from datetime import datetime, time, timedelta
import pytz
from odoo import models, api, fields


class FoodFlowCockpit(models.AbstractModel):
    _name = "foodflow.cockpit"
    _description = "FoodFlow Restaurant Cockpit Data"

    def _user_day_start_utc(self, day):
        """Naive-UTC datetime for midnight of ``day`` in the user's timezone.

        ``date_order`` is stored in UTC, but "today" is the user's local day.
        Building the boundary from ``context_today`` directly would mix a local
        date with a UTC comparison and drop late-evening orders (e.g. 21:00 UTC
        is already tomorrow in UTC+3). Localize then convert so the KPIs, the
        trend chart and the source-mix doughnut all agree.
        """
        tz = pytz.timezone(self.env.user.tz or "UTC")
        local_midnight = tz.localize(datetime.combine(day, time.min))
        return local_midnight.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def get_data(self):
        """One round-trip payload for the OWL cockpit dashboard."""
        today = fields.Date.context_today(self)
        today_start = self._user_day_start_utc(today)

        # Today's POS sales (paid/done/invoiced orders created today).
        pos_today = self.env["pos.order"].search([
            ("date_order", ">=", today_start),
            ("state", "in", ("paid", "done", "invoiced")),
        ])
        today_sales = sum(pos_today.mapped("amount_total"))

        # Open orders = draft POS orders in non-closed sessions.
        open_orders = self.env["pos.order"].search_count([
            ("state", "=", "draft"),
        ])

        # Tables currently occupied across open sessions.
        tables_in_use = 0
        if "restaurant.table" in self.env:
            tables_in_use = self.env["pos.order"].search_count([
                ("state", "=", "draft"),
                ("table_id", "!=", False),
            ])

        # Low-stock storable POS products (qty <= 5).
        low_stock_count = 0
        pos_prods = self.env["product.template"].search([
            ("available_in_pos", "=", True), ("is_storable", "=", True)])
        for p in pos_prods:
            if (p.qty_available or 0.0) <= 5.0:
                low_stock_count += 1

        paid_states = ("paid", "done", "invoiced")
        cfg = self.env["foodflow.config"].search(
            [("active", "=", True), ("connector_enabled", "=", True)], limit=1)
        connector_enabled = bool(cfg)
        foodflow_orders_today = 0
        if connector_enabled:
            # Count today's *paid* FoodFlow-sourced orders so this KPI stays
            # consistent with today_sales and the source-mix doughnut below;
            # unpaid/draft online orders still in the kitchen are reflected in
            # the "Open Orders" tile, not here.
            foodflow_orders_today = self.env["pos.order"].search_count([
                ("date_order", ">=", today_start),
                ("state", "in", paid_states),
                ("foodflow_id", "!=", False),
            ])

        # ── 7-day sales trend (oldest → today) ────────────────────────────
        week_start = self._user_day_start_utc(today - timedelta(days=6))
        week_orders = self.env["pos.order"].search([
            ("date_order", ">=", week_start),
            ("state", "in", paid_states),
        ])
        day_totals = {today - timedelta(days=i): 0.0 for i in range(6, -1, -1)}
        for o in week_orders:
            d = fields.Datetime.context_timestamp(self, o.date_order).date()
            if d in day_totals:
                day_totals[d] += o.amount_total
        trend_days = sorted(day_totals)
        sales_trend = {
            "labels": [d.strftime("%a") for d in trend_days],
            "values": [round(day_totals[d], 2) for d in trend_days],
        }

        # ── Top 5 items by quantity sold this week ────────────────────────
        line_groups = self.env["pos.order.line"]._read_group(
            [("order_id", "in", week_orders.ids), ("product_id", "!=", False)],
            groupby=["product_id"], aggregates=["qty:sum"],
            order="qty:sum desc", limit=5)
        top_items = {
            "labels": [product.display_name for product, _qty in line_groups],
            "values": [round(qty or 0.0, 1) for _product, qty in line_groups],
        }

        # ── Order source mix today (in-house POS vs FoodFlow online) ──────
        pos_today_count = len(pos_today)
        source_mix = {
            "labels": ["In-house", "FoodFlow"],
            "values": [
                max(pos_today_count - foodflow_orders_today, 0),
                foodflow_orders_today,
            ],
        }

        currency = self.env.company.currency_id
        return {
            "today_sales": float(today_sales),
            "open_orders": int(open_orders),
            "tables_in_use": int(tables_in_use),
            "low_stock_count": int(low_stock_count),
            "connector_enabled": connector_enabled,
            "foodflow_orders_today": int(foodflow_orders_today),
            "currency_symbol": currency.symbol or "",
            "sales_trend": sales_trend,
            "top_items": top_items,
            "source_mix": source_mix,
        }
