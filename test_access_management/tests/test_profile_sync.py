from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProfileSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_a = cls.env.ref('base.group_partner_manager')
        cls.group_b = cls.env.ref('base.group_no_one')
        cls.model = cls.env.ref('base.model_res_partner')
        cls.user = cls.env['res.users'].create({'name': 'Sync User', 'login': 'sync_user'})
        cls.profile_1 = cls._make_profile('P1', cls.group_a)
        cls.profile_2 = cls._make_profile('P2', cls.group_a, cls.group_b)

    @classmethod
    def _make_profile(cls, name, *groups):
        return cls.env['test.access.profile'].create({
            'name': name,
            'line_ids': [
                Command.create({'name': f'{name}-{g.id}', 'model_id': cls.model.id, 'group_id': g.id})
                for g in groups
            ],
        })

    def test_adding_profile_grants_groups(self):
        self.user.test_profile_ids = [Command.link(self.profile_2.id)]
        self.assertIn(self.group_a, self.user.group_ids)
        self.assertIn(self.group_b, self.user.group_ids)

    def test_removing_profile_revokes_unshared_groups(self):
        self.user.test_profile_ids = [Command.set([self.profile_1.id, self.profile_2.id])]
        self.user.test_profile_ids = [Command.unlink(self.profile_2.id)]
        self.assertIn(self.group_a, self.user.group_ids)
        self.assertNotIn(self.group_b, self.user.group_ids)

    def test_manual_group_is_never_removed(self):
        self.user.group_ids = [Command.link(self.group_a.id)]
        self.user.test_profile_ids = [Command.link(self.profile_1.id)]
        self.user.test_profile_ids = [Command.clear()]
        self.assertIn(self.group_a, self.user.group_ids)

    def test_line_change_recalculates_users(self):
        self.profile_1.user_ids = [Command.link(self.user.id)]
        self.profile_1.line_ids = [Command.create({
            'name': 'extra', 'model_id': self.model.id, 'group_id': self.group_b.id,
        })]
        self.assertIn(self.group_b, self.user.group_ids)
        self.profile_1.line_ids.filtered(lambda l: l.group_id == self.group_b).unlink()
        self.assertNotIn(self.group_b, self.user.group_ids)

    def test_profile_side_user_removal_and_unlink(self):
        self.profile_2.user_ids = [Command.link(self.user.id)]
        self.assertIn(self.group_b, self.user.group_ids)
        self.profile_2.unlink()
        self.assertNotIn(self.group_b, self.user.group_ids)

    def test_combined_lines(self):
        self.user.test_profile_ids = [Command.set([self.profile_1.id, self.profile_2.id])]
        self.assertEqual(
            self.user.test_profile_line_ids,
            self.profile_1.line_ids | self.profile_2.line_ids,
        )
