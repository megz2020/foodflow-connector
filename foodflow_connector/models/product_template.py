from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    foodflow_id = fields.Char(index=True, copy=False)
    foodflow_external_id = fields.Char(index=True, copy=False)
    foodflow_updated_at = fields.Datetime(copy=False)
    foodflow_synced_at = fields.Datetime(copy=False)
