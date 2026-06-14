from odoo import models, fields, _
from odoo.exceptions import UserError
from ..lib.client import FoodFlowClient, FoodFlowError


class FoodFlowSetupWizard(models.TransientModel):
    _name = "foodflow.setup.wizard"
    _description = "FoodFlow Setup Wizard"

    # XML ids of the starter products shipped in data/starter_menu.xml
    _STARTER_PRODUCT_XMLIDS = [
        "foodflow_connector.starter_prod_burger",
        "foodflow_connector.starter_prod_pizza",
        "foodflow_connector.starter_prod_fries",
        "foodflow_connector.starter_prod_cola",
    ]

    # ── restaurant setup (always shown) ───────────────────────────────────
    restaurant_name = fields.Char(
        required=True, default="My Restaurant",
        help="Name for the POS / restaurant created in Odoo.")
    table_count = fields.Integer(
        string="Number of tables", default=8,
        help="Tables created on the main dining floor.")
    create_pos = fields.Boolean(
        string="Create POS, floor, tables & payments", default=True)
    seed_sample = fields.Boolean(
        string="Seed a starter menu if catalog is empty", default=True)

    # ── FoodFlow online sync (revealed by the toggle) ─────────────────────
    connector_enabled = fields.Boolean(
        string="I also sell on FoodFlow (enable online sync)", default=False)
    base_url = fields.Char(default="https://app.foodflow/api/pos/v1")
    api_token = fields.Char()
    import_menu = fields.Boolean(
        string="Import menu from FoodFlow now", default=True)

    def action_test(self):
        self.ensure_one()
        if not self.base_url or not self.api_token:
            raise UserError(_("Enter the FoodFlow Base URL and API Token first."))
        try:
            FoodFlowClient(self.base_url, self.api_token).health()
        except FoodFlowError as e:
            raise UserError(_("Connection failed: %s") % e)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": _("Connection OK"), "type": "success"}}

    def action_apply(self):
        self.ensure_one()
        config = None
        if self.create_pos:
            config = self._provision_pos()
            self._provision_floor_tables(config)
            self._provision_payment_methods(config.company_id)
        if self.seed_sample:
            self._seed_starter_menu()
        self._mark_products_storable()

        if self.connector_enabled:
            if not self.base_url or not self.api_token:
                raise UserError(
                    _("FoodFlow Base URL and API Token are required to enable "
                      "online sync."))
            cfg = self.env["foodflow.config"].search(
                [("base_url", "=", self.base_url)], limit=1)
            if not cfg:
                cfg = self.env["foodflow.config"].create(
                    {"base_url": self.base_url})
            cfg.write({
                "base_url": self.base_url, "api_token": self.api_token,
                "active": True, "sync_enabled": True, "connector_enabled": True,
                "pos_config_id": config.id if config else cfg.pos_config_id.id,
            })
            if self.import_menu:
                self.env["foodflow.sync"]._pull_menu(cfg)

        return self.env["ir.actions.actions"]._for_xml_id(
            "foodflow_connector.action_foodflow_cockpit")

    def _provision_payment_methods(self, company):
        PM = self.env["pos.payment.method"]
        methods = self.env["pos.payment.method"]
        # journal_id may be left False when a company has no cash/bank journal
        # yet (e.g. accounting not configured); the method is still usable for
        # provisioning and a journal can be set later.
        cash = PM.search([("name", "=", "Cash"),
                          ("company_id", "=", company.id)], limit=1)
        if not cash:
            cash_journal = self.env["account.journal"].search(
                [("type", "=", "cash"), ("company_id", "=", company.id)], limit=1)
            cash = PM.create({
                "name": "Cash", "is_cash_count": True,
                "company_id": company.id,
                "journal_id": cash_journal.id if cash_journal else False})
        methods |= cash
        card = PM.search([("name", "=", "Card"),
                          ("company_id", "=", company.id)], limit=1)
        if not card:
            bank_journal = self.env["account.journal"].search(
                [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
            card = PM.create({
                "name": "Card", "is_cash_count": False,
                "company_id": company.id,
                "journal_id": bank_journal.id if bank_journal else False})
        methods |= card
        return methods

    def _provision_pos(self):
        Pos = self.env["pos.config"]
        company = self.env.company
        existing = Pos.search([
            ("name", "=", self.restaurant_name),
            ("company_id", "=", company.id)], limit=1)
        if existing:
            return existing
        methods = self._provision_payment_methods(company)
        config = Pos.create({
            "name": self.restaurant_name,
            "company_id": company.id,
            "module_pos_restaurant": True,
            "payment_method_ids": [(6, 0, methods.ids)],
        })
        return config

    def _provision_floor_tables(self, config):
        self.ensure_one()
        Floor = self.env["restaurant.floor"]
        Table = self.env["restaurant.table"]
        floor = Floor.search([
            ("name", "=", "Main Floor"),
            ("pos_config_ids", "in", config.id)], limit=1)
        if not floor:
            floor = Floor.create({
                "name": "Main Floor",
                "pos_config_ids": [(6, 0, [config.id])],
            })
        missing = max(0, self.table_count - len(floor.table_ids))
        start = len(floor.table_ids)
        for i in range(missing):
            n = start + i + 1
            Table.create({
                "table_number": n,
                "floor_id": floor.id,
                "seats": 4,
                # lay tables out on a 5-per-row grid (120px spacing)
                "position_h": 50 + (i % 5) * 120,
                "position_v": 50 + (i // 5) * 120,
            })
        return floor

    def _mark_products_storable(self):
        # Odoo 19: storability is the boolean `is_storable` on a `consu` product
        # (the legacy type='product' was merged into consu + is_storable).
        prods = self.env["product.template"].search([
            ("available_in_pos", "=", True)])
        to_fix = prods.filtered(lambda p: not p.is_storable)
        if to_fix:
            to_fix.write({"is_storable": True})
        return prods

    def _seed_starter_menu(self):
        """Activate the shipped starter menu only when no POS product exists.

        The records live in data/starter_menu.xml (noupdate) so they survive
        upgrades; here we just (re)flag them available when the catalog is bare."""
        existing = self.env["product.template"].search_count(
            [("available_in_pos", "=", True)])
        if existing:
            return False
        prods = self.env["product.template"]
        for xmlid in self._STARTER_PRODUCT_XMLIDS:
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec:
                rec.write({"available_in_pos": True, "sale_ok": True})
                prods |= rec
        return bool(prods)
