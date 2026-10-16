from odoo import api, fields, models


class IrAccess(models.Model):
    _inherit = 'ir.access'

    uam_user_count = fields.Integer(string='Users', compute='_compute_uam_user_count', compute_sudo=True)

    @api.depends('group_id.all_user_ids')
    def _compute_uam_user_count(self):
        for access in self:
            access.uam_user_count = len(access.group_id.all_user_ids)

    def action_open_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Users with this access'),
            'res_model': 'res.users',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('user_access_management.user_list_view').id, 'list'),
                (self.env.ref('user_access_management.user_form_view').id, 'form'),
            ],
            'domain': [('all_group_ids', 'in', self.group_id.ids)],
        }

    def _uam_snapshot(self):
        self.ensure_one()
        return '%s | group: %s | operation: %s | domain: %s' % (
            self.model_id.model,
            self.group_id.full_name or 'none',
            self.operation,
            self.domain or 'none',
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for access in records:
            self.env['access.change.log']._log(
                'create', 'access', access.name, 'Access right', '', access._uam_snapshot())
        return records

    def write(self, vals):
        old = {access.id: access._uam_snapshot() for access in self}
        res = super().write(vals)
        for access in self:
            new = access._uam_snapshot()
            if new != old[access.id]:
                self.env['access.change.log']._log(
                    'edit', 'access', access.name, 'Access right', old[access.id], new)
        return res

    def unlink(self):
        for access in self:
            self.env['access.change.log']._log(
                'delete', 'access', access.name, 'Access right', access._uam_snapshot(), '')
        return super().unlink()
