from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    uam_stale_login_days = fields.Integer(
        string='Stale Login After (days)',
        config_parameter='user_access_management.stale_login_days',
        default=3,
    )
    uam_print_retention_days = fields.Integer(
        string='Keep downloaded PDFs (days)',
        config_parameter='user_access_management.print_retention_days',
        default=180,
        help="Older Print Log entries and their PDFs are deleted nightly. 0 keeps them forever.",
    )
