from odoo import Command, api, fields, models
from odoo.exceptions import AccessError


class TestAccessProfile(models.Model):
    _name = 'test.access.profile'
    _description = 'Access Profile'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many(
        'res.users',
        relation='test_access_profile_user_rel',
        column1='profile_id',
        column2='user_id',
        string='Users',
    )
    line_ids = fields.One2many('test.access.profile.line', 'profile_id', string='Access Lines')

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles.user_ids._test_sync_profile_groups()
        return profiles

    def write(self, vals):
        users = self.user_ids
        result = super().write(vals)
        if {'user_ids', 'line_ids', 'active'} & vals.keys():
            (users | self.user_ids)._test_sync_profile_groups()
        return result

    def unlink(self):
        self.write({'user_ids': [Command.clear()]})
        return super().unlink()

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only administrators can do this.'))

    def action_export_xlsx(self):
        self.ensure_one()
        self._check_admin()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/test_access_management/export/profile/{self.id}',
            'target': 'self',
        }

    def action_open_upload(self):
        self.ensure_one()
        self._check_admin()
        return self.env['test.access.profile.upload']._open_action(profile_id=self.id)
