from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

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
