import time
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install', 'test_administration')
class TestAdministration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref('base.group_partner_manager')
        cls.user = cls.env['res.users'].create({
            'name': 'Temp Tester', 'login': 'temp_tester',
            'group_ids': [Command.set([cls.env.ref('base.group_user').id])],
        })

    def test_activity_logged(self):
        before = self.env['admin.activity'].search_count([('user_id', '=', self.user.id)])
        self.env['res.partner'].with_user(self.env.ref('base.user_admin')).create({'name': 'Logged'})
        self.assertEqual(self.env['admin.activity'].search_count([('user_id', '=', self.env.ref('base.user_admin').id),
                                                                  ('model_name', '=', 'res.partner'),
                                                                  ('action', '=', 'create')]) > 0, True)
        self.assertEqual(self.env['admin.activity'].search_count([('user_id', '=', self.user.id)]), before)

    def test_temp_access_grant_and_expire(self):
        now = fields.Datetime.now()
        rec = self.env['admin.temp.access'].create({
            'user_id': self.user.id, 'group_ids': [Command.set(self.group.ids)],
            'date_from': now - timedelta(minutes=5), 'date_to': now + timedelta(hours=1)})
        self.assertEqual(rec.state, 'active')
        self.assertIn(self.group, self.user.group_ids)
        rec.date_to = now - timedelta(minutes=1)
        self.env['admin.temp.access']._cron_sync()
        self.assertEqual(rec.state, 'expired')
        self.assertNotIn(self.group, self.user.group_ids)

    def test_temp_access_keeps_held_group(self):
        self.user.group_ids = [Command.link(self.group.id)]
        now = fields.Datetime.now()
        rec = self.env['admin.temp.access'].create({
            'user_id': self.user.id, 'group_ids': [Command.set(self.group.ids)],
            'date_from': now - timedelta(minutes=5), 'date_to': now + timedelta(hours=1)})
        rec.action_cancel()
        self.assertIn(self.group, self.user.group_ids)

    def test_simulation_report(self):
        wiz = self.env['admin.access.simulation'].create({'user_id': self.user.id})
        self.assertIn('Temp Tester', wiz.report_html)
        self.assertIn('Contact', wiz.report_html)

    def test_weekly_summary(self):
        self.env['res.partner'].with_user(self.env.ref('base.user_admin')).create({'name': 'Weekly'})
        wiz = self.env['admin.weekly.summary'].create({})
        self.assertIn('Contact', wiz.summary_html)

    def test_inactive_alert(self):
        self.user.write({'inactive_alert_days': 1})
        self.env.cr.execute("UPDATE res_users SET create_date = now() - interval '3 days' WHERE id = %s", [self.user.id])
        self.user.invalidate_recordset()
        self.env['res.users']._cron_inactive_alert()
        self.assertTrue(self.env['admin.alert'].search([('user_id', '=', self.user.id), ('resolved', '=', False)]))

    def test_single_session_revokes_others(self):
        now = fields.Datetime.now()
        self.env['res.device.log'].create({
            'session_identifier': 'a' * 42, 'user_id': self.user.id, 'ip_address': '1.1.1.1',
            'user_agent': 'ua', 'first_activity': now, 'last_activity': now})
        self.user.single_session = True
        self.user._after_session_login()
        self.assertTrue(self.env['res.device.log'].search([('session_identifier', '=', 'a' * 42)]).revoked)

    def test_dashboard(self):
        action = self.env['admin.dashboard'].action_open()
        dash = self.env['admin.dashboard'].browse(action['res_id'])
        dash.now_html, dash.online_count


@tagged('post_install', '-at_install', 'test_administration')
class TestIdleLogout(HttpCase):

    def test_idle_logout(self):
        user = self.env['res.users'].create({
            'name': 'Idle', 'login': 'idle_user', 'password': 'idle_user',
            'group_ids': [Command.set([self.env.ref('base.group_user').id])], 'idle_timeout': 1})
        session = self.authenticate('idle_user', 'idle_user')
        self.assertEqual(self.url_open('/odoo').status_code, 200)
        self.assertTrue(self.session.get('admin_last_seen') or self.session.uid)
        session['admin_last_seen'] = time.time() - 3600
        from odoo.http.session import session_store
        session_store().save(session)
        res = self.url_open('/web/session/get_session_info', data='{}', headers={'Content-Type': 'application/json'})
        self.assertNotEqual(res.json().get('result', {}).get('uid'), user.id)
