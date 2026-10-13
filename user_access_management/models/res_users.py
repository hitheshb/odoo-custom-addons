from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools import SQL, format_datetime


class ResUsers(models.Model):
    _inherit = 'res.users'

    uam_access_ids = fields.Many2many(
        'ir.access', string='Effective Access Rights',
        compute='_compute_uam_access_ids', compute_sudo=True, groups='base.group_system',
    )

    uam_login_stale = fields.Boolean(compute='_compute_uam_login_stale', search='_search_uam_login_stale')
    uam_group_count = fields.Integer(string='Group Count', compute='_compute_uam_counts', compute_sudo=True)
    uam_access_count = fields.Integer(string='Access Right Count', compute='_compute_uam_counts', compute_sudo=True)

    uam_last_work = fields.Char(compute='_compute_uam_last_work', compute_sudo=True, groups='base.group_system')
    uam_current_page = fields.Char('Current Page', readonly=True, groups='base.group_system')
    uam_last_seen = fields.Datetime('Last Seen', readonly=True, groups='base.group_system')

    uam_lock_count = fields.Integer(compute='_compute_uam_stats', compute_sudo=True, groups='base.group_system')
    uam_temp_count = fields.Integer(compute='_compute_uam_stats', compute_sudo=True, groups='base.group_system')
    uam_print_count = fields.Integer(compute='_compute_uam_stats', compute_sudo=True, groups='base.group_system')
    uam_usage_count = fields.Integer(compute='_compute_uam_stats', compute_sudo=True, groups='base.group_system')
    uam_change_count = fields.Integer(compute='_compute_uam_stats', compute_sudo=True, groups='base.group_system')
    uam_timeline_html = fields.Html(compute='_compute_uam_timeline_html', sanitize=False, compute_sudo=True, groups='base.group_system')

    @api.model
    def uam_track(self, model, action, page):
        if not model and action:
            acts = self.env['ir.actions.act_window'].sudo()
            if isinstance(action, int) or (isinstance(action, str) and action.isascii() and action.isdigit()):
                act = acts.browse(int(action)).exists()
            elif isinstance(action, str) and '.' in action:
                act = self.env.ref(action, raise_if_not_found=False)
                act = act.sudo() if act is not None and act._name == 'ir.actions.act_window' else acts
            elif isinstance(action, str):
                act = acts.search([('path', '=', action)], limit=1)
            else:
                act = acts
            model = act.res_model
        # the client controls `model`: keep only real, non-transient models
        if not isinstance(model, str) or model not in self.env or self.env[model]._transient:
            model = False
        self.env.cr.execute(SQL('UPDATE res_users SET uam_current_page = %s, uam_last_seen = %s WHERE id = %s',
                                (page or '')[:250], fields.Datetime.now(), self.env.uid))
        if model:
            self.env['uam.model.usage']._bump(self.env.uid, model)
        return True

    @api.model
    def _uam_set_home_action(self):
        action = self.env.ref('user_access_management.uam_dashboard_action')
        admins = self.sudo().search([('group_ids', 'in', self.env.ref('base.group_system').ids), ('action_id', '=', False)])
        admins.write({'action_id': action.id})

    def _compute_uam_last_work(self):
        for user in self:
            last = self.env['user.work.update'].search(
                [('user_id', '=', user.id), ('skipped', '=', False)], limit=1)
            user.uam_last_work = last.text

    def _uam_stale_limit(self):
        days = self.env['ir.config_parameter'].sudo().get_int('user_access_management.stale_login_days', 3)
        return fields.Datetime.now() - timedelta(days=days)

    def _compute_uam_login_stale(self):
        limit = self._uam_stale_limit()
        for user in self:
            user.uam_login_stale = not user.login_date or user.login_date < limit

    def _search_uam_login_stale(self, operator, value):
        if operator in ('in', 'not in'):
            positive = (True in value) == (operator == 'in')
        elif operator in ('=', '!='):
            positive = bool(value) == (operator == '=')
        else:
            return NotImplemented
        # stale == no login log at/after the limit (login_date is the related first log, so don't search it)
        recent = [('create_date', '>=', self._uam_stale_limit())]
        return [('log_ids', 'not any' if positive else 'any', recent)]

    @api.depends('all_group_ids.access_ids')
    def _compute_uam_access_ids(self):
        for user in self:
            user.uam_access_ids = user.all_group_ids.access_ids

    @api.depends('all_group_ids', 'uam_access_ids')
    def _compute_uam_counts(self):
        for user in self:
            user.uam_group_count = len(user.all_group_ids)
            user.uam_access_count = len(user.uam_access_ids)

    def action_uam_open_groups(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Groups of %s', self.name),
            'res_model': 'res.groups',
            'view_mode': 'list,form',
            'views': [(self.env.ref('user_access_management.group_list_view').id, 'list'),
                      (self.env.ref('user_access_management.group_form_view').id, 'form')],
            'domain': [('id', 'in', self.all_group_ids.ids)],
        }

    def action_uam_open_access(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Access Rights of %s', self.name),
            'res_model': 'ir.access',
            'view_mode': 'list,form',
            'views': [(self.env.ref('user_access_management.access_list_view').id, 'list'),
                      (self.env.ref('user_access_management.access_form_view').id, 'form')],
            'domain': [('id', 'in', self.uam_access_ids.ids)],
        }

    def _uam_change_domain(self):
        return ['|', ('target_user_id', '=', self.id),
                '&', ('target_user_id', '=', False), '&', ('target_kind', '=', 'user'), ('target_name', '=', self.name)]

    def _uam_lock_domain(self):
        return ['|', ('user_id', '=', self.id), ('group_id', 'in', self.all_group_ids.ids)]

    def _compute_uam_stats(self):
        for user in self:
            user.uam_lock_count = self.env['uam.access.lock'].search_count(user._uam_lock_domain())
            user.uam_temp_count = self.env['user.temp.access'].search_count([('user_id', '=', user.id)])
            user.uam_print_count = self.env['uam.print.log'].search_count([('user_id', '=', user.id)])
            user.uam_usage_count = self.env['uam.model.usage'].search_count([('user_id', '=', user.id)])
            user.uam_change_count = self.env['access.change.log'].search_count(user._uam_change_domain())

    def _uam_open(self, name, model, domain):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    def action_uam_open_locks(self):
        return self._uam_open(self.env._('Locks'), 'uam.access.lock', self._uam_lock_domain())

    def action_uam_open_temp(self):
        return self._uam_open(self.env._('Temporary Access'), 'user.temp.access', [('user_id', '=', self.id)])

    def action_uam_open_prints(self):
        return self._uam_open(self.env._('Prints'), 'uam.print.log', [('user_id', '=', self.id)])

    def action_uam_open_usage(self):
        return self._uam_open(self.env._('Model Usage'), 'uam.model.usage', [('user_id', '=', self.id)])

    def action_uam_open_changes(self):
        return self._uam_open(self.env._('Changes'), 'access.change.log', self._uam_change_domain())

    TIMELINE_LIMIT = 50

    def _uam_timeline_events(self):
        """(utc datetime, badge modifier, sentence) tuples, newest first."""
        self.ensure_one()
        ev = []
        for c in self.env['access.change.log'].search(self._uam_change_domain(), limit=self.TIMELINE_LIMIT):
            what = c.new_value or c.old_value
            ev.append((c.date, 'online' if c.action == 'add' else 'alert',
                       self.env._('%(action)s %(label)s: %(what)s (by %(by)s)', action=c.action.capitalize(),
                                  label=c.field_label or '', what=what or '', by=c.acting_user_id.name or '')))
        for lock in self.env['uam.access.lock'].with_context(active_test=False).search(
                self._uam_lock_domain(), limit=self.TIMELINE_LIMIT):
            target = lock.user_id.name or lock.group_id.full_name
            ev.append((lock.create_date, 'alert', self.env._('Locked %(methods)s on %(model)s (%(target)s)',
                       methods=', '.join(lock.method_ids.mapped('label')), model=lock.model_id.name, target=target)))
        for t in self.env['user.temp.access'].search([('user_id', '=', self.id)], limit=self.TIMELINE_LIMIT):
            ev.append((t.date_from, 'away', self.env._('Temporary access %(groups)s until %(until)s (%(state)s)',
                       groups=', '.join(t.group_ids.mapped('full_name')),
                       until=format_datetime(self.env, t.date_to), state=t.state)))
        for p in self.env['uam.print.log'].search([('user_id', '=', self.id)], limit=self.TIMELINE_LIMIT):
            ev.append((p.create_date, 'accent', self.env._('Downloaded %(doc)s (%(label)s)',
                       doc=p.record_name or p.res_ids[:50], label=p.label)))
        return sorted((e for e in ev if e[0]), key=lambda e: e[0], reverse=True)[:self.TIMELINE_LIMIT]

    def _compute_uam_timeline_html(self):
        for user in self:
            rows = Markup('').join(
                Markup('<li class="d-flex gap-3 py-1"><span class="text-muted text-nowrap">%s</span>'
                       '<span class="o_uam_badge o_uam_badge--%s">&#9679;</span><span>%s</span></li>')
                % (format_datetime(self.env, when), kind, text)
                for when, kind, text in user._uam_timeline_events())
            user.uam_timeline_html = (Markup('<ul class="list-unstyled mb-0">%s</ul>') % rows if rows
                                      else Markup('<p class="text-muted">Nothing has happened for this user yet.</p>'))

    def _uam_log_groups(self, old_ids, new_ids, user):
        groups = self.env['res.groups']
        for action, ids in (('add', set(new_ids) - set(old_ids)), ('remove', set(old_ids) - set(new_ids))):
            for group in groups.browse(ids):
                self.env['access.change.log']._log(
                    action, 'user', user.name, 'Groups',
                    '' if action == 'add' else group.full_name,
                    group.full_name if action == 'add' else '', user_id=user.id)

    def _log_group_changes(self, vals, old_group_ids, editing_groups=None):                # overriding base method
        for user in self.sudo():
            self._uam_log_groups(old_group_ids[user.id], user.group_ids.ids, user)
        return super()._log_group_changes(vals, old_group_ids, editing_groups)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users.sudo():
            self._uam_log_groups([], user.group_ids.ids, user)
        return users
