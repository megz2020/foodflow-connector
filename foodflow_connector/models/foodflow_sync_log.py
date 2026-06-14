from odoo import models, fields


class FoodFlowSyncLog(models.Model):
    _name = "foodflow.sync.log"
    _description = "FoodFlow Sync Log"
    _order = "create_date desc"

    direction = fields.Selection(
        [("pull", "Pull"), ("push", "Push")], required=True)
    resource = fields.Selection(
        [("menu", "Menu"), ("orders", "Orders")], required=True)
    created_count = fields.Integer(default=0)
    updated_count = fields.Integer(default=0)
    failed_count = fields.Integer(default=0)
    error_detail = fields.Text()
