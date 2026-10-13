from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


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
