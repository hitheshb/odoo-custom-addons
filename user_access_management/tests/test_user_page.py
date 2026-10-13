from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestUserPage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='uam_page_user', groups='base.group_user,base.group_partner_manager')
        cls.group = cls.env['res.groups'].create({'name': '<b>x</b>'})
        partner_model = cls.env['ir.model']._get('res.partner')
        methods = cls.env['uam.lock.method']._sync_for_model('res.partner')
        cls.env['uam.access.lock'].create({'user_id': cls.user.id, 'model_id': partner_model.id, 'forever': True,
                                           'method_ids': [(6, 0, methods[:1].ids)]})
        cls.env['uam.access.lock'].create({'group_id': cls.group.id, 'model_id': partner_model.id, 'forever': True,
                                           'method_ids': [(6, 0, methods[:1].ids)]})
        cls.env['user.temp.access'].create({'user_id': cls.user.id, 'group_ids': [(6, 0, cls.group.ids)],
                                            'date_to': fields.Datetime.now() + timedelta(days=1)})

    def test_counts(self):
        self.user.invalidate_recordset()
        self.assertEqual(self.user.uam_lock_count, 2)   # direct + via group (temp access added the group)
        self.assertEqual(self.user.uam_temp_count, 1)
        for name in ('locks', 'temp', 'prints', 'usage', 'changes'):
            self.assertEqual(getattr(self.user, f'action_uam_open_{name}')()['type'], 'ir.actions.act_window')

    def test_timeline_escapes(self):
        html = str(self.user.uam_timeline_html)
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', html)
        self.assertNotIn('<b>x</b>', html)
        self.assertIn('Temporary access', html)
        self.assertIn('Locked', html)
