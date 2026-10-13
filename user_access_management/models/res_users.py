from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import SQL


class ResUsers(models.Model):
    _inherit = 'res.users'

    uam_access_ids = fields.Many2many(
        'ir.access', string='Effective Access Rights',
        compute='_compute_uam_access_ids', compute_sudo=True,
    )

    uam_login_stale = fields.Boolean(compute='_compute_uam_login_stale', search='_search_uam_login_stale')
    uam_group_count = fields.Integer(string='Group Count', compute='_compute_uam_counts', compute_sudo=True)
    uam_access_count = fields.Integer(string='Access Right Count', compute='_compute_uam_counts', compute_sudo=True)

    uam_last_work = fields.Char(compute='_compute_uam_last_work', compute_sudo=True)
    uam_current_page = fields.Char('Current Page', readonly=True)
    uam_last_seen = fields.Datetime('Last Seen', readonly=True)

    @api.model
    def uam_track(self, model, action, page):
        if not model and action:
            acts = self.env['ir.actions.act_window'].sudo()
            act = acts.browse(int(action)).exists() if str(action).isdigit() else acts.search([('path', '=', action)], limit=1)
            model = act.res_model
        self.env.cr.execute(SQL('UPDATE res_users SET uam_current_page = %s, uam_last_seen = %s WHERE id = %s',
                                (page or '')[:250], fields.Datetime.now(), self.env.uid))
        if model:
            self.env['uam.model.usage']._bump(self.env.uid, model)
        return True

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

    def _uam_log_groups(self, old_ids, new_ids, user):
        groups = self.env['res.groups']
        for action, ids in (('add', set(new_ids) - set(old_ids)), ('remove', set(old_ids) - set(new_ids))):
            for group in groups.browse(ids):
                self.env['access.change.log']._log(
                    action, 'user', user.name, 'Groups',
                    '' if action == 'add' else group.full_name,
                    group.full_name if action == 'add' else '')

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
