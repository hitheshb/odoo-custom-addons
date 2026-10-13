from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestStaleLogin(TransactionCase):

    def _login_days_ago(self, user, days):
        log = self.env['res.users.log'].with_user(user).sudo().create({})
        self.env.cr.execute("UPDATE res_users_log SET create_uid = %s, create_date = %s WHERE id = %s",
                            (user.id, fields.Datetime.now() - timedelta(days=days), log.id))
        self.env.invalidate_all()

    def test_threshold_from_settings(self):
        user = new_test_user(self.env, login='uam_stale_user')
        self._login_days_ago(user, 5)
        param = self.env['ir.config_parameter'].sudo()
        stale = [('uam_login_stale', '=', True), ('id', '=', user.id)]

        param.set_int('user_access_management.stale_login_days', 3)
        self.assertTrue(user.uam_login_stale)
        self.assertEqual(self.env['res.users'].search(stale), user)

        param.set_int('user_access_management.stale_login_days', 7)
        user.invalidate_recordset(['uam_login_stale'])
        self.assertFalse(user.uam_login_stale)
        self.assertFalse(self.env['res.users'].search(stale))
        self.assertEqual(self.env['res.users'].search([('uam_login_stale', '=', False), ('id', '=', user.id)]), user)

    def test_recent_login_among_old_ones_not_stale(self):
        user = new_test_user(self.env, login='uam_mixed_user')
        self._login_days_ago(user, 5)
        self._login_days_ago(user, 0)
        self.env['ir.config_parameter'].sudo().set_int('user_access_management.stale_login_days', 3)
        self.assertFalse(user.uam_login_stale)
        self.assertFalse(self.env['res.users'].search([('uam_login_stale', '=', True), ('id', '=', user.id)]))
        self.assertEqual(self.env['res.users'].search([('uam_login_stale', '=', False), ('id', '=', user.id)]), user)

    def test_never_logged_in_is_stale(self):
        user = new_test_user(self.env, login='uam_never_user')
        user.log_ids.unlink()
        self.assertFalse(user.log_ids)
        self.assertTrue(user.uam_login_stale)
        self.assertEqual(self.env['res.users'].search([('uam_login_stale', '=', True), ('id', '=', user.id)]), user)

    def _stale_user(self, login):
        user = new_test_user(self.env, login=login, email=f'{login}@example.com')
        self._login_days_ago(user, 30)
        return user

    def test_archive_skips_fresh_admins_and_self(self):
        stale = self._stale_user('uam_stale_a')
        fresh = new_test_user(self.env, login='uam_fresh_a')
        self._login_days_ago(fresh, 0)
        admin = self.env.ref('base.user_admin')
        self._login_days_ago(admin, 30)
        res = (stale | fresh | admin).with_user(admin).action_uam_archive_stale()
        self.assertFalse(stale.active)
        self.assertTrue(fresh.active)
        self.assertTrue(admin.active)
        self.assertIn('Archived 1', res['params']['message'])

    def test_remind_sends_mail_only_to_stale(self):
        stale = self._stale_user('uam_stale_b')
        fresh = new_test_user(self.env, login='uam_fresh_b', email='uam_fresh_b@example.com')
        self._login_days_ago(fresh, 0)
        Mail = self.env['mail.mail']
        count = lambda email: Mail.search_count([('recipient_ids.email', '=', email)])
        before = count('uam_stale_b@example.com')
        res = (stale | fresh).action_uam_remind_stale()
        self.assertEqual(count('uam_stale_b@example.com') - before, 1)
        self.assertEqual(count('uam_fresh_b@example.com'), 0)
        self.assertIn('Sent 1', res['params']['message'])

    def test_non_admin_cannot_archive_or_remind(self):
        stale = self._stale_user('uam_stale_c')
        plain = new_test_user(self.env, login='uam_plain_c', groups='base.group_user')
        with self.assertRaises(AccessError):
            stale.with_user(plain).action_uam_archive_stale()
        with self.assertRaises(AccessError):
            stale.with_user(plain).action_uam_remind_stale()
        self.assertTrue(stale.active)
