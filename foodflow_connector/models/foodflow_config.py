from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..lib.client import FoodFlowClient, FoodFlowError


class FoodFlowConfig(models.Model):
    _name = "foodflow.config"
    _description = "FoodFlow Connection"

    name = fields.Char(default="FoodFlow", required=True)
    base_url = fields.Char(required=True, help="e.g. https://app.foodflow/api/pos/v1")
    api_token = fields.Char(string="API Token", help="ff_live_… token")
    active = fields.Boolean(default=True)
    sync_enabled = fields.Boolean(default=True)
    connector_enabled = fields.Boolean(
        string="FoodFlow Online Sync",
        default=False,
        help="Enable two-way sync with the FoodFlow online platform. "
             "Leave off for a standalone in-restaurant setup.")
    sync_interval_minutes = fields.Integer(default=10)
    last_menu_sync_at = fields.Datetime(readonly=True)
    last_order_sync_at = fields.Datetime(readonly=True)
    sync_in_progress = fields.Boolean(default=False, readonly=True)
    conflict_policy = fields.Selection(
        [("last_write_wins", "Last write wins")],
        default="last_write_wins", required=True)
    pos_config_id = fields.Many2one(
        "pos.config", string="POS",
        help="POS used to host orders synced from FoodFlow.")

    @api.model
    def get_active(self):
        cfg = self.search([("active", "=", True)], limit=1)
        if not cfg:
            raise UserError(_("No active FoodFlow configuration. Run the setup wizard."))
        return cfg

    def get_client(self):
        self.ensure_one()
        if not self.base_url or not self.api_token:
            raise UserError(_("FoodFlow base URL and token are required."))
        return FoodFlowClient(self.base_url, self.api_token)

    def action_test_connection(self):
        self.ensure_one()
        try:
            self.get_client().health()
        except FoodFlowError as e:
            raise UserError(_("Connection failed: %s") % e)
        return self._notify(_("Connection OK"))

    # ── manual sync actions ───────────────────────────────────────────────
    def action_sync_now(self):
        self.ensure_one()
        return self.env["foodflow.sync"]._run_for(
            self, ("pull", "push"), ("menu", "orders"))

    def action_pull_menu(self):
        self.ensure_one()
        return self.env["foodflow.sync"]._run_for(self, ("pull",), ("menu",))

    def action_push_menu(self):
        self.ensure_one()
        return self.env["foodflow.sync"]._run_for(self, ("push",), ("menu",))

    def action_sync_orders(self):
        self.ensure_one()
        return self.env["foodflow.sync"]._run_for(
            self, ("pull", "push"), ("orders",))

    def _notify(self, msg):
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"message": msg, "type": "success", "sticky": False},
        }
