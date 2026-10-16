from odoo import Command, api, fields, models
from odoo.exceptions import AccessError


class ResUsers(models.Model):
    _inherit = 'res.users'

    test_profile_ids = fields.Many2many(
        'test.access.profile',
        relation='test_access_profile_user_rel',
        column1='user_id',
        column2='profile_id',
        string='Access Profiles',
        groups='base.group_system',
    )
    test_profile_line_ids = fields.Many2many(
        'test.access.profile.line',
        compute='_compute_profile_line_ids',
        string='Combined Access Lines',
        groups='base.group_system',
    )

    @api.depends('test_profile_ids.active', 'test_profile_ids.line_ids')
    def _compute_profile_line_ids(self):
        for user in self:
            user.test_profile_line_ids = user.test_profile_ids.filtered('active').line_ids

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users.filtered('test_profile_ids')._test_sync_profile_groups()
        return users

    def write(self, vals):
        result = super().write(vals)
        if 'test_profile_ids' in vals:
            self._test_sync_profile_groups()
        return result

    def _test_sync_profile_groups(self):
        grants = self.env['test.access.profile.grant'].sudo()
        for user in self.sudo():
            needed = {
                (group.id, profile.id)
                for profile in user.test_profile_ids.filtered('active')
                for group in profile.line_ids.group_id
            }
            needed_groups = {group_id for group_id, _profile_id in needed}
            existing = grants.search([('user_id', '=', user.id)])
            existing_pairs = {(g.group_id.id, g.profile_id.id) for g in existing}
            known_groups = set(existing.group_id.ids)
            manual_groups = set(existing.filtered('was_manual').group_id.ids)
            held = set(user.group_ids.ids)

            stale = existing.filtered(
                lambda g: (g.group_id.id, g.profile_id.id) not in needed
            )
            groups_to_remove = set(stale.group_id.ids) - needed_groups - manual_groups
            groups_to_add = needed_groups - held

            new_rows = []
            for group_id, profile_id in needed - existing_pairs:
                if group_id in known_groups:
                    was_manual = group_id in manual_groups
                else:
                    was_manual = group_id in held
                new_rows.append({
                    'user_id': user.id,
                    'group_id': group_id,
                    'profile_id': profile_id,
                    'was_manual': was_manual,
                })

            stale.unlink()
            grants.create(new_rows)
            user.group_ids = (
                [Command.link(group_id) for group_id in groups_to_add]
                + [Command.unlink(group_id) for group_id in groups_to_remove]
            )

    def _check_profile_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only administrators can do this.'))

    def action_export_profiles_xlsx(self):
        self.ensure_one()
        self._check_profile_admin()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/test_access_management/export/user/{self.id}',
            'target': 'self',
        }

    def action_open_profile_upload(self):
        self.ensure_one()
        self._check_profile_admin()
        return self.env['test.access.profile.upload']._open_action(user_id=self.id)

    def action_open_profile_tab(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('test_access_management.res_users_view_form_profile_tab').id, 'form')],
            'target': 'current',
        }

    def action_open_access_import(self):
        self.ensure_one()
        self._check_profile_admin()
        return self.env['test.access.import'].create({'user_id': self.id})._reopen()

    def action_export_groups_xlsx(self):
        self.ensure_one()
        self._check_profile_admin()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/test_access_management/export/groups/{self.id}',
            'target': 'self',
        }
