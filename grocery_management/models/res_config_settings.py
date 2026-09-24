from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    grocery_low_stock_threshold = fields.Integer(
        string="Low Stock Threshold",
        config_parameter="grocery_management.low_stock_threshold",
        default=10,
    )

    grocery_expiry_warning_days = fields.Integer(
        string="Expiry Warning Window (days)",
        config_parameter="grocery_management.expiry_warning_days",
        default=3,
        help="The daily expiry check flags products expiring within this many days.",
    )
