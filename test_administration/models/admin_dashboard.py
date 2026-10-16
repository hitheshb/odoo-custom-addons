from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models


class AdminDashboard(models.TransientModel):
    _name = 'admin.dashboard'
    _description = 'Administration Dashboard'

    online_count = fields.Integer(compute='_compute_stats')
    away_count = fields.Integer(compute='_compute_stats')
    multi_session_count = fields.Integer(compute='_compute_stats')
    alert_count = fields.Integer(compute='_compute_stats')
    temp_active_count = fields.Integer(compute='_compute_stats')
    temp_expiring_count = fields.Integer(compute='_compute_stats')
    activity_today = fields.Integer(compute='_compute_stats')
    now_html = fields.Html(compute='_compute_now_html', sanitize=False)

    @api.model
    def action_open(self):
        rec = self.create({})
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Administration Dashboard'),
            'res_model': self._name, 'res_id': rec.id, 'view_mode': 'form', 'target': 'current',
        }

    @api.depends()
    def _compute_stats(self):
        env = self.env
        now = fields.Datetime.now()
        Users = env['res.users'].sudo()
        stats = {
            'online_count': Users.search_count([('admin_last_seen', '>', now - timedelta(minutes=5))]),
            'away_count': Users.search_count([('admin_last_seen', '<=', now - timedelta(minutes=5)),
                                              ('admin_last_seen', '>', now - timedelta(minutes=30))]),
            'multi_session_count': sum(1 for n in Users._admin_session_counts().values() if n > 1),
            'alert_count': env['admin.alert'].search_count([('resolved', '=', False)]),
            'temp_active_count': env['admin.temp.access'].search_count([('state', '=', 'active')]),
            'temp_expiring_count': env['admin.temp.access'].search_count(
                [('state', '=', 'active'), ('date_to', '<', now + timedelta(hours=24))]),
            'activity_today': env['admin.activity'].search_count(
                [('create_date', '>=', now.replace(hour=0, minute=0, second=0, microsecond=0))]),
        }
        for rec in self:
            rec.update(stats)

    @api.depends()
    def _compute_now_html(self):
        emps = self.env['hr.employee'].search([('user_id', '!=', False)])
        rows = [Markup('<tr><td>%s</td><td>%s</td></tr>') % (e.name, e.admin_status)
                for e in emps.sorted(lambda e: e.admin_status or '')]
        html = Markup('<table class="table table-sm"><thead><tr><th>Employee</th><th>Doing now</th></tr></thead>'
                      '<tbody>%s</tbody></table>') % Markup('').join(rows)
        for rec in self:
            rec.now_html = html

    def _act(self, name, model, domain):
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'view_mode': 'list,form', 'domain': domain}

    def action_online(self):
        limit = fields.Datetime.now() - timedelta(minutes=30)
        return self._act(self.env._('Active users'), 'res.users', [('admin_last_seen', '>', limit)])

    def action_sessions(self):
        ids = [uid for uid, n in self.env['res.users']._admin_session_counts().items() if n > 1]
        return self._act(self.env._('Users with several sessions'), 'res.session', [('user_id', 'in', ids)])

    def action_alerts(self):
        return self._act(self.env._('Alerts'), 'admin.alert', [('resolved', '=', False)])

    def action_temp(self):
        return self._act(self.env._('Active temporary access'), 'admin.temp.access', [('state', '=', 'active')])

    def action_activity(self):
        return self.env['ir.actions.act_window']._for_xml_id('test_administration.admin_activity_action')
