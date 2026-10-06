from odoo import api, fields, models


class AccessChangeLog(models.Model):
    _name = 'access.change.log'
    _description = 'Access Change Log'
    _order = 'id desc'

    date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    acting_user_id = fields.Many2one('res.users', string='Changed By', readonly=True)
    action = fields.Selection(
        [('create', 'Create'), ('edit', 'Edit'), ('delete', 'Delete'), ('add', 'Add'), ('remove', 'Remove')],
        required=True, readonly=True,
    )
    target_kind = fields.Selection(
        [('user', 'User'), ('group', 'Group'), ('access', 'Access Right')],
        required=True, readonly=True,
    )
    target_name = fields.Char(readonly=True)
    field_label = fields.Char(readonly=True)
    old_value = fields.Text(readonly=True)
    new_value = fields.Text(readonly=True)

    @api.model
    def _log(self, action, kind, name, label='', old='', new=''):
        if self.env.context.get('install_mode'):
            return
        self.sudo().create({
            'acting_user_id': self.env.uid,
            'action': action,
            'target_kind': kind,
            'target_name': name,
            'field_label': label,
            'old_value': old,
            'new_value': new,
        })
