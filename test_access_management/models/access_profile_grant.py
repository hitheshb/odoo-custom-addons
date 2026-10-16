from odoo import fields, models


class TestAccessProfileGrant(models.Model):
    _name = 'test.access.profile.grant'
    _description = 'Group granted to a user by an access profile'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    group_id = fields.Many2one('res.groups', required=True, ondelete='cascade', index=True)
    profile_id = fields.Many2one('test.access.profile', required=True, ondelete='cascade', index=True)
    was_manual = fields.Boolean(
        help='The user already had this group before any profile granted it.',
    )

    _user_group_profile_uniq = models.Constraint(
        'UNIQUE (user_id, group_id, profile_id)',
        'The same group is already recorded for this user and profile.',
    )
