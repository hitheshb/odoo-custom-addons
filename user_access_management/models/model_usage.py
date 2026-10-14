from odoo import api, fields, models
from odoo.tools import SQL


class UamModelUsage(models.Model):
    _name = 'uam.model.usage'
    _description = 'Model Usage per Day'
    _order = 'date desc, last_seen desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, ondelete='cascade', index=True)
    model = fields.Char('Technical Model', required=True, readonly=True)
    model_name = fields.Char('Model', compute='_compute_model_name')
    date = fields.Date(required=True, readonly=True, index=True)
    view_count = fields.Integer('Views', readonly=True)
    first_seen = fields.Datetime(readonly=True)
    last_seen = fields.Datetime(readonly=True)

    _uniq_day = models.Constraint('UNIQUE(user_id, model, date)', 'One usage row per user, model and day.')

    @api.depends('model')
    def _compute_model_name(self):
        names = {m.model: m.name for m in self.env['ir.model'].sudo().search([('model', 'in', self.mapped('model'))])}
        for row in self:
            row.model_name = names.get(row.model, row.model)

    @api.depends('user_id', 'model_name', 'date')
    def _compute_display_name(self):
        for row in self:
            row.display_name = f'{row.user_id.name} – {row.model_name} – {row.date}'

    @api.model
    def _bump(self, user_id, model):
        now = fields.Datetime.now()
        self.env.cr.execute(SQL("""
            INSERT INTO uam_model_usage (user_id, model, date, view_count, first_seen, last_seen,
                                         create_uid, write_uid, create_date, write_date)
            VALUES (%(u)s, %(m)s, %(d)s, 1, %(n)s, %(n)s, %(u)s, %(u)s, %(n)s, %(n)s)
            ON CONFLICT (user_id, model, date)
            DO UPDATE SET view_count = uam_model_usage.view_count + 1, last_seen = EXCLUDED.last_seen
        """, u=user_id, m=model, d=fields.Date.context_today(self), n=now))
