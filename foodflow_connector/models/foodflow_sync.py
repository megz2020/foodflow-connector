import logging
from datetime import datetime
from odoo import models, api, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def _parse_dt(value):
    """Parse FoodFlow ISO-8601 (with Z) into naive UTC datetime for comparison."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class FoodFlowSync(models.AbstractModel):
    _name = "foodflow.sync"
    _description = "FoodFlow Sync Engine"

    # ── orchestration ─────────────────────────────────────────────────────
    @api.model
    def _run_for(self, cfg, directions, resources):
        cfg.sync_in_progress = True
        try:
            if "menu" in resources and "pull" in directions:
                self._pull_menu(cfg)
            if "menu" in resources and "push" in directions:
                self._push_menu(cfg)
            if "orders" in resources and "pull" in directions:
                self._pull_orders(cfg)
            if "orders" in resources and "push" in directions:
                self._push_orders(cfg)
        finally:
            cfg.sync_in_progress = False
        return cfg._notify("Sync complete")

    @api.model
    def cron_run(self):
        configs = self.env["foodflow.config"].search(
            [("active", "=", True), ("sync_enabled", "=", True),
             ("connector_enabled", "=", True)])
        for cfg in configs:
            if not cfg.sync_in_progress:
                self._run_for(cfg, ("pull", "push"), ("menu", "orders"))

    # ── last-write-wins helper ────────────────────────────────────────────
    def _remote_wins(self, record, remote_updated):
        """Apply remote only if it has advanced since the remote state we last
        applied.

        We compare the incoming ``updated_at`` against the stored
        ``foodflow_updated_at`` (the last remote revision we wrote locally), so
        both sides of the comparison live in FoodFlow's clock domain. Comparing
        against our own ``write_date`` would be wrong: every pull bumps
        ``write_date``, mixing two clocks and silently dropping genuinely-newer
        remote edits."""
        if not record:
            return True
        remote_dt = _parse_dt(remote_updated)
        if remote_dt is None:
            return False
        if not record.foodflow_updated_at:
            return True
        # ties → no change to apply (we already hold this remote revision)
        return remote_dt > record.foodflow_updated_at

    # ── menu pull ─────────────────────────────────────────────────────────
    @api.model
    def _pull_menu(self, cfg):
        client = cfg.get_client()
        created = updated = 0
        cat_by_ff = {}
        for rc in client.list_categories():
            cat, did = self._upsert_category_from_remote(rc)
            cat_by_ff[rc["id"]] = cat
            created += did == "created"
            updated += did == "updated"
        for ri in client.list_items():
            _, did = self._upsert_item_from_remote(ri, cat_by_ff, client)
            created += did == "created"
            updated += did == "updated"
        cfg.last_menu_sync_at = fields.Datetime.now()
        self.env["foodflow.sync.log"].create({
            "direction": "pull", "resource": "menu",
            "created_count": created, "updated_count": updated})

    def _upsert_category_from_remote(self, rc):
        Cat = self.env["pos.category"]
        rec = Cat.search([("foodflow_id", "=", rc["id"])], limit=1)
        if rec and not self._remote_wins(rec, rc.get("updated_at")):
            return rec, "skipped"
        vals = {
            "name": rc["name"],
            "sequence": rc.get("display_order") or 0,
            "foodflow_id": rc["id"],
            "foodflow_external_id": (rc.get("pos_metadata") or {}).get("external_id"),
            "foodflow_updated_at": _parse_dt(rc.get("updated_at")),
            "foodflow_synced_at": fields.Datetime.now(),
        }
        if rec:
            rec.write(vals)
            return rec, "updated"
        return Cat.create(vals), "created"

    def _upsert_item_from_remote(self, ri, cat_by_ff, client=None):
        Prod = self.env["product.template"]
        rec = Prod.search([("foodflow_id", "=", ri["id"])], limit=1)
        if rec and not self._remote_wins(rec, ri.get("updated_at")):
            return rec, "skipped"
        cat = cat_by_ff.get(ri.get("category_id"))
        vals = {
            "name": ri["name"],
            "list_price": float(ri.get("price") or 0.0),
            "available_in_pos": True,
            "sale_ok": True,
            "foodflow_id": ri["id"],
            "foodflow_external_id": (ri.get("pos_metadata") or {}).get("external_id"),
            "foodflow_updated_at": _parse_dt(ri.get("updated_at")),
            "foodflow_synced_at": fields.Datetime.now(),
        }
        # Pull the item photo (best-effort) only when we're about to write the
        # record anyway, so unchanged items don't trigger a download each poll.
        if client is not None and ri.get("image_url"):
            image_b64 = client.fetch_image_b64(ri["image_url"])
            if image_b64:
                vals["image_1920"] = image_b64
        if cat:
            vals["pos_categ_ids"] = [(6, 0, [cat.id])]
        if rec:
            rec.write(vals)
            return rec, "updated"
        return Prod.create(vals), "created"

    # ── menu push ─────────────────────────────────────────────────────────
    @api.model
    def _push_menu(self, cfg):
        client = cfg.get_client()
        created = updated = 0
        prods = self.env["product.template"].search([
            ("available_in_pos", "=", True)])
        for prod in prods:
            if prod.foodflow_synced_at and prod.write_date <= prod.foodflow_synced_at:
                continue  # unchanged since last sync → skip (avoids echo loop)
            had_ff_id = bool(prod.foodflow_id)
            ext = prod.foodflow_external_id or f"odoo-prod-{prod.id}"
            payload = {
                "name": prod.name,
                "price": round(prod.list_price, 2),
                "isAvailable": True,
                "isActive": True,
                "externalId": ext,
            }
            remote = client.upsert_item(payload, ff_id=prod.foodflow_id or None)
            prod.write({
                "foodflow_id": remote.get("id") or prod.foodflow_id,
                "foodflow_external_id": ext,
                "foodflow_updated_at": _parse_dt(remote.get("updated_at")),
                "foodflow_synced_at": fields.Datetime.now(),
            })
            updated += had_ff_id
            created += not had_ff_id
        self.env["foodflow.sync.log"].create({
            "direction": "push", "resource": "menu",
            "created_count": created, "updated_count": updated})

    # ── pos session helper ────────────────────────────────────────────────
    @api.model
    def _ensure_pos_session(self, cfg):
        """Return an open pos.session to host FoodFlow orders, creating one if needed."""
        config = cfg.pos_config_id
        if not config:
            config = self.env["pos.config"].search(
                [("name", "=", "FoodFlow POS")], limit=1) \
                or self.env["pos.config"].search([], limit=1)
        if not config:
            raise ValidationError(
                "No POS configuration available. Run the FoodFlow setup wizard first.")
        session = self.env["pos.session"].search(
            [("config_id", "=", config.id),
             ("state", "not in", ("closed", "closing_control"))],
            limit=1)
        if not session:
            session = self.env["pos.session"].create({"config_id": config.id})
        if session.state == "opening_control":
            session.action_pos_session_open()
        return session

    @api.model
    def _order_header_vals(self, session, ro):
        """Minimal required pos.order header fields for an inbound FoodFlow order."""
        total = float(ro.get("total") or 0.0)
        return {
            "session_id": session.id,
            "company_id": session.config_id.company_id.id,
            "pricelist_id": session.config_id.pricelist_id.id
            or session.config_id.available_pricelist_ids[:1].id,
            "amount_tax": 0.0,
            "amount_total": total,
            "amount_paid": 0.0,
            "amount_return": 0.0,
        }

    # ── order pull ────────────────────────────────────────────────────────
    @api.model
    def _pull_orders(self, cfg):
        client = cfg.get_client()
        # FoodFlow validates `since` with Zod's .datetime() which requires a
        # UTC-suffixed ISO-8601 string. Odoo stores naive UTC datetimes, so we
        # format to seconds precision and append the Z.
        since = (cfg.last_order_sync_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                 if cfg.last_order_sync_at else None)
        created = updated = 0
        Order = self.env["pos.order"]
        session = None
        for ro in client.list_orders(since=since):
            rec = Order.search([("foodflow_id", "=", ro["id"])], limit=1)
            vals = {
                "foodflow_id": ro["id"],
                "foodflow_external_id": ro.get("external_id"),
                "foodflow_status": ro.get("status"),
                "foodflow_updated_at": _parse_dt(ro.get("updated_at")),
                "foodflow_synced_at": fields.Datetime.now(),
            }
            if rec:
                if self._remote_wins(rec, ro.get("updated_at")):
                    rec.write(vals)
                    updated += 1
            else:
                if session is None:
                    session = self._ensure_pos_session(cfg)
                vals.update(self._order_header_vals(session, ro))
                Order.create(vals)
                created += 1
        cfg.last_order_sync_at = fields.Datetime.now()
        self.env["foodflow.sync.log"].create({
            "direction": "pull", "resource": "orders",
            "created_count": created, "updated_count": updated})

    # ── order push ────────────────────────────────────────────────────────
    @api.model
    def _push_orders(self, cfg):
        client = cfg.get_client()
        pushed = 0
        new_orders = self.env["pos.order"].search([("foodflow_id", "=", False)])
        for order in new_orders:
            ext = order.foodflow_external_id or f"odoo-order-{order.id}"
            partner = order.partner_id
            items = []
            for l in order.lines:
                if not l.product_id:
                    continue
                tmpl = l.product_id.product_tmpl_id
                item = {
                    "name": l.product_id.display_name or tmpl.name,
                    "quantity": int(l.qty or 1),
                    "unitPrice": round(l.price_unit or 0.0, 2),
                }
                # Link back to the FoodFlow menu item when we know its UUID.
                if tmpl.foodflow_id:
                    item["menuItemId"] = tmpl.foodflow_id
                items.append(item)
            if not items:
                items = [{"name": "POS item", "quantity": 1,
                          "unitPrice": round(order.amount_total or 0.0, 2)}]
            payload = {
                "orderType": "dine_in",
                "items": items,
                "customerName": (partner.name if partner else None) or "Walk-in",
            }
            if partner and partner.phone:
                payload["customerPhone"] = partner.phone
            remote = client.create_order(payload)
            remote = remote.get("order", remote)
            order.write({
                "foodflow_id": remote.get("id"),
                "foodflow_external_id": ext,
                "foodflow_status": remote.get("status"),
                "foodflow_synced_at": fields.Datetime.now(),
            })
            pushed += 1
        self.env["foodflow.sync.log"].create({
            "direction": "push", "resource": "orders",
            "created_count": pushed})
