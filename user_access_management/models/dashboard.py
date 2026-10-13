from datetime import timedelta

from odoo import api, fields, models


class UamDashboard(models.AbstractModel):
    _name = 'uam.dashboard'
    _description = 'User Access Dashboard'

    def _users(self):
        return self.env['res.users'].sudo().search([('share', '=', False)])

    def _tile_domains(self):
        now = fields.Datetime.now()
        users = self._users()
        today = fields.Datetime.to_string(fields.Datetime.start_of(now, 'day'))
        return {
            'online': ('res.users', [('id', 'in', users.filtered(lambda u: u.im_status == 'online').ids)]),
            'away': ('res.users', [('id', 'in', users.filtered(lambda u: u.im_status == 'away').ids)]),
            'stale': ('res.users', [('share', '=', False), ('uam_login_stale', '=', True)]),
            'locks': ('uam.access.lock', [('active', '=', True)]),
            'temp_expiring': ('user.temp.access', [('state', '=', 'active'), ('date_to', '<', now + timedelta(hours=24))]),
            'prints_today': ('uam.print.log', [('create_date', '>=', today)]),
        }

    @api.model
    def get_data(self, date=False):
        day = fields.Date.to_date(date) if date else fields.Date.context_today(self)
        labels = {'online': ('Online', 'fa-circle text-success'), 'away': ('Away', 'fa-circle text-warning'),
                  'stale': ('Stale logins', 'fa-exclamation-triangle text-danger'),
                  'locks': ('Active locks', 'fa-lock'), 'temp_expiring': ('Temp access expiring <24h', 'fa-clock-o'),
                  'prints_today': ('PDFs today', 'fa-print')}
        tiles = [{'key': k, 'label': labels[k][0], 'icon': labels[k][1],
                  'count': self.env[m].sudo().search_count(d)} for k, (m, d) in self._tile_domains().items()]
        order = {'online': 0, 'away': 1}
        users = sorted(self._users(), key=lambda u: (order.get(u.im_status, 2), u.name))
        usage = self.env['uam.model.usage'].sudo().search([('date', '=', day)], order='view_count desc', limit=50)
        prints = self.env['uam.print.log'].sudo().search([], limit=10)
        dt = fields.Datetime.to_string
        return {
            'date': fields.Date.to_string(day),
            'tiles': tiles,
            'users': [{'id': u.id, 'name': u.name, 'status': u.im_status, 'page': u.uam_current_page or '',
                       'last_seen': dt(u.uam_last_seen) if u.uam_last_seen else False,
                       'login_date': dt(u.login_date) if u.login_date else False,
                       'stale': u.uam_login_stale} for u in users],
            'usage': [{'user_id': r.user_id.id, 'user': r.user_id.name, 'model': r.model,
                       'model_name': r.model_name, 'views': r.view_count, 'last_seen': dt(r.last_seen)} for r in usage],
            'prints': [{'id': p.id, 'document': p.record_name or p.res_ids[:50], 'label': p.label,
                        'user': p.user_id.name, 'date': dt(p.create_date),
                        'url': f'/web/content/{p.attachment_id.id}?download=true'} for p in prints],
        }

    @api.model
    def open_tile(self, key):
        model, domain = self._tile_domains()[key]
        return {'type': 'ir.actions.act_window', 'name': key.replace('_', ' ').title(), 'res_model': model,
                'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    @api.model
    def open_user_usage(self, user_id, date):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Model Usage'), 'res_model': 'uam.model.usage',
                'views': [(False, 'list')], 'domain': [('user_id', '=', user_id), ('date', '=', date)]}
