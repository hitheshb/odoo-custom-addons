from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTempWarning(TransactionCase):

    def test_my_expiring_only_own(self):
        a = new_test_user(self.env, login='uam_tw_a')
        b = new_test_user(self.env, login='uam_tw_b')
        group = self.env['res.groups'].create({'name': 'UAM TW'})
        TA = self.env['user.temp.access']
        TA.create({'user_id': a.id, 'group_ids': [(6, 0, group.ids)], 'date_to': fields.Datetime.now() + timedelta(hours=5)})
        TA.create({'user_id': b.id, 'group_ids': [(6, 0, group.ids)], 'date_to': fields.Datetime.now() + timedelta(days=3)})
        mine = TA.with_user(a).uam_my_expiring()
        self.assertEqual(len(mine), 1)
        self.assertIn('UAM TW', mine[0]['groups'])
        self.assertTrue(4 < mine[0]['hours_left'] <= 5)
        self.assertEqual(len(TA.with_user(b).uam_my_expiring()), 1)

    def test_my_expiring_skips_past_and_scheduled(self):
        u = new_test_user(self.env, login='uam_tw_d')
        group = self.env['res.groups'].create({'name': 'UAM TW3'})
        TA = self.env['user.temp.access']
        now = fields.Datetime.now()
        past = TA.create({'user_id': u.id, 'group_ids': [(6, 0, group.ids)], 'date_to': now + timedelta(hours=2)})
        self.env.cr.execute("UPDATE user_temp_access SET date_to = %s WHERE id = %s", (now - timedelta(minutes=5), past.id))
        TA.create({'user_id': u.id, 'group_ids': [(6, 0, group.ids)],
                   'date_from': now + timedelta(days=1), 'date_to': now + timedelta(days=2)})
        self.env.invalidate_all()
        self.assertEqual(past.state, 'active')
        self.assertEqual(TA.with_user(u).uam_my_expiring(), [])
        live = TA.create({'user_id': u.id, 'group_ids': [(6, 0, group.ids)], 'date_to': now + timedelta(hours=3)})
        rows = TA.with_user(u).uam_my_expiring()
        self.assertEqual([r['id'] for r in rows], [live.id])
        self.assertTrue(rows[0]['until'])

    def test_time_left_pct(self):
        u = new_test_user(self.env, login='uam_tw_c')
        group = self.env['res.groups'].create({'name': 'UAM TW2'})
        now = fields.Datetime.now()
        t = self.env['user.temp.access'].create({'user_id': u.id, 'group_ids': [(6, 0, group.ids)],
                                                'date_from': now - timedelta(hours=5), 'date_to': now + timedelta(hours=5)})
        self.assertTrue(45 <= t.uam_time_left_pct <= 55)
        self.assertTrue(t.uam_ending_soon)
