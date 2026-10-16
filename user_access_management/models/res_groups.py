from odoo import api, fields, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    uam_group_type = fields.Selection(
        [('normal', 'Normal'), ('template', 'Template'), ('role', 'Role Wrapper'),
         ('switch', 'Flag')],
        string='Type', compute='_compute_uam_group_type', compute_sudo=True,
        help="Groups with no rights of their own: Template = new-user defaults, Role Wrapper = rights come "
             "from implied groups, Flag = only shows or hides parts of the screen.")
    uam_color = fields.Integer(compute='_compute_uam_group_type', compute_sudo=True)  # tag colour index per type
    uam_user_count = fields.Integer(string='User Count', compute='_compute_uam_counts', compute_sudo=True)
    uam_access_count = fields.Integer(string='Access Rights', compute='_compute_uam_counts', compute_sudo=True)

    @api.depends('all_user_ids', 'access_ids')
    def _compute_uam_counts(self):
        for group in self:
            group.uam_user_count = len(group.all_user_ids)
            group.uam_access_count = len(group.access_ids)

    @api.depends('access_ids', 'implied_ids', 'all_implied_ids.access_ids')
    def _compute_uam_group_type(self):
        template = self.env.ref('base.default_user_group', raise_if_not_found=False)
        for group in self:
            if group.access_ids:
                kind = 'normal'
            elif group == template:
                kind = 'template'
            elif group.all_implied_ids.access_ids:
                kind = 'role'
            else:
                kind = 'switch'
            group.uam_group_type = kind
            group.uam_color = {'template': 4, 'role': 3, 'switch': 10}.get(kind, 0)

    def action_uam_open_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Users in %s', self.full_name),
            'res_model': 'res.users',
            'view_mode': 'kanban,list,form',
            'views': [(self.env.ref('user_access_management.user_kanban_view').id, 'kanban'),
                      (self.env.ref('user_access_management.user_list_view').id, 'list'),
                      (self.env.ref('user_access_management.user_form_view').id, 'form')],
            'domain': [('all_group_ids', 'in', self.ids)],
        }

    def action_uam_open_access(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Access Rights of %s', self.full_name),
            'res_model': 'ir.access',
            'view_mode': 'list,form',
            'views': [(self.env.ref('user_access_management.access_list_view').id, 'list'),
                      (self.env.ref('user_access_management.access_form_view').id, 'form')],
            'domain': [('group_id', '=', self.id)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        for group in groups:
            self.env['access.change.log']._log('create', 'group', group.full_name)
        return groups

    def write(self, vals):
        if 'implied_ids' not in vals:
            return super().write(vals)
        old = {group.id: set(group.implied_ids.ids) for group in self}
        res = super().write(vals)
        for group in self:
            new = set(group.implied_ids.ids)
            for action, ids in (('add', new - old[group.id]), ('remove', old[group.id] - new)):
                for implied in self.browse(ids):
                    self.env['access.change.log']._log(
                        action, 'group', group.full_name, 'Implied groups',
                        '' if action == 'add' else implied.full_name,
                        implied.full_name if action == 'add' else '')
        return res

    def unlink(self):
        for group in self:
            self.env['access.change.log']._log('delete', 'group', group.full_name)
        return super().unlink()
