from odoo import models, fields


class PosCategory(models.Model):
    _inherit = "pos.category"

    foodflow_id = fields.Char(index=True, copy=False)
    foodflow_external_id = fields.Char(index=True, copy=False)
    foodflow_updated_at = fields.Datetime(copy=False)
    foodflow_synced_at = fields.Datetime(copy=False)
