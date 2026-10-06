from odoo import fields, models


class AdminAlert(models.Model):
    _name = 'admin.alert'
    _description = 'Administration Alert'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    message = fields.Char(required=True)
    resolved = fields.Boolean(default=False)
    create_date = fields.Datetime('Raised', readonly=True)

    def action_resolve(self):
        self.write({'resolved': True})
