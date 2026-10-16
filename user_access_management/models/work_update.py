from datetime import timedelta

from odoo import api, fields, models


class UserWorkUpdate(models.Model):
    _name = 'user.work.update'
    _description = 'User Work Update'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, ondelete='cascade')
    date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    text = fields.Text(readonly=True)
    skipped = fields.Boolean(readonly=True)

    @api.model
    def uam_is_due(self):
        """True if the current user has no update (answered or skipped) in the last 3 hours."""
        return not self.sudo().search_count([
            ('user_id', '=', self.env.uid),
            ('date', '>', fields.Datetime.now() - timedelta(hours=3)),
        ])

    @api.model
    def uam_submit(self, text):
        text = (text or '').strip()
        self.sudo().create({'user_id': self.env.uid, 'text': text, 'skipped': not text})
