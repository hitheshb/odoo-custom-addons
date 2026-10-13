from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    uam_stale_login_days = fields.Integer(
        string='Stale Login After (days)',
        config_parameter='user_access_management.stale_login_days',
        default=3,
    )
