from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    uam_access_ids = fields.Many2many(
        'ir.access', string='Effective Access Rights',
        compute='_compute_uam_access_ids', compute_sudo=True,
    )

    @api.depends('all_group_ids.access_ids')
    def _compute_uam_access_ids(self):
        for user in self:
            user.uam_access_ids = user.all_group_ids.access_ids

    def _uam_log_groups(self, old_ids, new_ids, user):
        groups = self.env['res.groups']
        for action, ids in (('add', set(new_ids) - set(old_ids)), ('remove', set(old_ids) - set(new_ids))):
            for group in groups.browse(ids):
                self.env['access.change.log']._log(
                    action, 'user', user.name, 'Groups',
                    '' if action == 'add' else group.full_name,
                    group.full_name if action == 'add' else '')

    def _log_group_changes(self, vals, old_group_ids, editing_groups=None):
        for user in self.sudo():
            self._uam_log_groups(old_group_ids[user.id], user.group_ids.ids, user)
        return super()._log_group_changes(vals, old_group_ids, editing_groups)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users.sudo():
            self._uam_log_groups([], user.group_ids.ids, user)
        return users
