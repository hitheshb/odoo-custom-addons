from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import format_datetime


@tagged('post_install', '-at_install')
class TestDashboard(TransactionCase):

    def test_get_data_shape(self):
        # TransactionCase runs as OdooBot (inactive), so track as the admin user instead
        admin = self.env.ref('base.user_admin')
        self.env['res.users'].with_user(admin).uam_track('res.partner', False, 'Contacts')
        data = self.env['uam.dashboard'].get_data(fields.Date.to_string(fields.Date.today()))
        self.assertEqual({t['key'] for t in data['tiles']},
                         {'online', 'away', 'stale', 'locks', 'temp_expiring', 'prints_today'})
        self.assertIn(admin.id, [u['id'] for u in data['users']])
        self.assertIn('res.partner', [u['model'] for u in data['usage']])

    def test_open_tile_returns_action(self):
        for key in ('online', 'away', 'stale', 'locks', 'temp_expiring', 'prints_today'):
            action = self.env['uam.dashboard'].open_tile(key)
            self.assertEqual(action['type'], 'ir.actions.act_window', key)

    def test_home_action_only_when_empty(self):
        admin = self.env.ref('base.user_admin')
        admin.action_id = False
        self.env['res.users']._uam_set_home_action()
        # action_id is an ir.actions.actions record, so compare ids
        self.assertEqual(admin.action_id.id, self.env.ref('user_access_management.uam_dashboard_action').id)

    def test_non_admin_denied(self):
        demo = self.env['res.users'].create({'name': 'Plain', 'login': 'plain_dash'})
        with self.assertRaises(AccessError):
            self.env['uam.dashboard'].with_user(demo).get_data()
        with self.assertRaises(AccessError):
            self.env['uam.dashboard'].with_user(demo).open_tile('online')

    def test_times_in_user_tz(self):
        admin = self.env.ref('base.user_admin')
        admin.tz = 'Asia/Kolkata'
        self.env['res.users'].with_user(admin).uam_track('res.partner', False, 'Contacts')
        self.env.invalidate_all()
        data = self.env['uam.dashboard'].with_user(admin).get_data()
        row = next(u for u in data['usage'] if u['model'] == 'res.partner' and u['user_id'] == admin.id)
        usage = self.env['uam.model.usage'].search([('user_id', '=', admin.id), ('model', '=', 'res.partner')],
                                                   order='date desc', limit=1)
        self.assertEqual(row['last_seen'], format_datetime(self.env, usage.last_seen, tz='Asia/Kolkata'))
        self.assertNotEqual(row['last_seen'], fields.Datetime.to_string(usage.last_seen))

    def test_prints_today_uses_user_tz(self):
        admin = self.env.ref('base.user_admin')
        admin.tz = 'Asia/Kolkata'   # UTC+5:30
        # 20:00 UTC on Oct 13 is 01:30 on Oct 14 in Kolkata, so "today" starts at Oct 13 18:30 UTC
        with patch('odoo.fields.Datetime.now', return_value=datetime(2026, 10, 13, 20, 0)):
            domain = self.env['uam.dashboard'].with_user(admin)._tile_domains()['prints_today'][1]
        self.assertEqual(domain, [('create_date', '>=', '2026-10-13 18:30:00')])

    def test_prints_today_dst_change_day(self):
        admin = self.env.ref('base.user_admin')
        admin.tz = 'America/New_York'   # DST starts 2026-03-08 02:00; midnight is still UTC-5
        with patch('odoo.fields.Datetime.now', return_value=datetime(2026, 3, 8, 12, 0)):
            domain = self.env['uam.dashboard'].with_user(admin)._tile_domains()['prints_today'][1]
        self.assertEqual(domain, [('create_date', '>=', '2026-03-08 05:00:00')])
