from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTracking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='uam_tracked')
        cls.Users = cls.env['res.users'].with_user(cls.user)

    def _usage(self):
        return self.env['uam.model.usage'].search([('user_id', '=', self.user.id), ('date', '=', fields.Date.today())])

    def test_track_counts_views(self):
        self.Users.uam_track('res.partner', False, 'Contacts')
        self.Users.uam_track('res.partner', False, 'Contacts / Azure')
        self.env.invalidate_all()
        usage = self._usage()
        self.assertEqual(usage.model, 'res.partner')
        self.assertEqual(usage.view_count, 2)
        self.assertEqual(self.user.uam_current_page, 'Contacts / Azure')
        self.assertTrue(self.user.uam_last_seen)

    def test_track_resolves_action_id(self):
        action = self.env['ir.actions.act_window'].search([('res_model', '=', 'res.partner')], limit=1)
        self.Users.uam_track(False, action.id, 'Contacts')
        self.env.invalidate_all()
        self.assertEqual(self._usage().model, 'res.partner')

    def test_track_without_model(self):
        self.Users.uam_track(False, 'not-a-path', 'Dashboard')
        self.env.invalidate_all()
        self.assertFalse(self._usage())
        self.assertEqual(self.user.uam_current_page, 'Dashboard')
