from odoo import models, fields

FOODFLOW_STATUSES = [
    ("pending", "Pending"), ("confirmed", "Confirmed"),
    ("preparing", "Preparing"), ("ready", "Ready"),
    ("out_for_delivery", "Out for delivery"),
    ("delivered", "Delivered"), ("cancelled", "Cancelled"),
]


class PosOrder(models.Model):
    _inherit = "pos.order"

    foodflow_id = fields.Char(index=True, copy=False)
    foodflow_external_id = fields.Char(index=True, copy=False)
    foodflow_status = fields.Selection(FOODFLOW_STATUSES, copy=False)
    foodflow_updated_at = fields.Datetime(copy=False)
    foodflow_synced_at = fields.Datetime(copy=False)
