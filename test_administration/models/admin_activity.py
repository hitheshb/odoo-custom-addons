from datetime import timedelta

from odoo import api, fields, models


class AdminActivity(models.Model):
    _name = 'admin.activity'
    _description = 'User Activity Log'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, readonly=True)
    model_name = fields.Char(required=True, index=True, readonly=True)
    model_id = fields.Many2one('ir.model', compute='_compute_model_id', string='Model')
    res_id = fields.Integer(readonly=True)
    action = fields.Selection(
        [('create', 'Created'), ('write', 'Updated'), ('unlink', 'Deleted')],
        required=True, readonly=True)
    count = fields.Integer(default=1, readonly=True)
    create_date = fields.Datetime('At', index=True, readonly=True)

    @api.depends('model_name')
    def _compute_model_id(self):
        models_by_name = {m.model: m for m in self.env['ir.model'].sudo().search(
            [('model', 'in', self.mapped('model_name'))])}
        for rec in self:
            rec.model_id = models_by_name.get(rec.model_name)

    @api.autovacuum
    def _gc_activity(self):
        limit = fields.Datetime.now() - timedelta(days=90)
        self.search([('create_date', '<', limit)]).unlink()
