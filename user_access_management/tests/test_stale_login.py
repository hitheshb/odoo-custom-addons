from datetime import timedelta

from odoo import fields
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
