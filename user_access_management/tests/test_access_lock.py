from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException


@tagged('post_install', '-at_install')
class TestAccessLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='uam_locked', groups='base.group_user,base.group_partner_manager')
        cls.other = new_test_user(cls.env, login='uam_free', groups='base.group_user,base.group_partner_manager')
        cls.Lock = cls.env['uam.access.lock']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.methods = cls.env['uam.lock.method']._sync_for_model('res.partner')

    def _lock(self, names, **vals):
        return self.Lock.create({
            'user_id': self.user.id, 'model_id': self.partner_model.id,
            'method_ids': [(6, 0, self.methods.filtered(lambda m: m.name in names).ids)],
            'forever': True, **vals,
        })

    def test_sync_contains_crud_and_print(self):
        self.assertTrue({'create', 'write', 'unlink', 'print'} <= set(self.methods.mapped('name')))
        self.assertEqual(self.env['uam.lock.method']._sync_for_model('res.partner'), self.methods)  # idempotent

    def test_web_save_maps_to_create_or_write(self):
        key = self.Lock._method_key
        self.assertEqual(key('web_save', [[], {}]), 'create')
        self.assertEqual(key('web_save', [[3], {}]), 'write')
        self.assertEqual(key('create', [{}]), 'create')
        self.assertEqual(key('action_archive', [[3]]), 'action_archive')

    def test_locked_user_blocked(self):
        self._lock(['create'])
        with self.assertRaises(UserError):
            self.Lock.with_user(self.user)._check('res.partner', 'web_save', [[], {}])
        self.Lock.with_user(self.user)._check('res.partner', 'web_save', [[1], {}])  # write still allowed

    def test_other_user_not_blocked(self):
        self._lock(['create'])
        self.Lock.with_user(self.other)._check('res.partner', 'create', [{}])

    def test_expired_lock_not_enforced(self):
        lock = self._lock(['create'], forever=False, date_until=fields.Datetime.now() + timedelta(hours=1))
        self.env.cr.execute("UPDATE uam_access_lock SET date_until = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(minutes=1), lock.id))
        self.env.invalidate_all()
        self.Lock.with_user(self.user)._check('res.partner', 'create', [{}])
        self.Lock._cron_archive_expired()
        self.assertFalse(lock.active)

    def test_needs_date_or_forever(self):
        with self.assertRaises(ValidationError):
            self._lock(['create'], forever=False)


@tagged('post_install', '-at_install')
class TestAccessLockHttp(HttpCase):

    def test_call_kw_blocked(self):
        user = new_test_user(self.env, login='uam_http_locked', password='uam_http_locked',
                             groups='base.group_user,base.group_partner_manager')
        methods = self.env['uam.lock.method']._sync_for_model('res.partner')
        self.env['uam.access.lock'].create({
            'user_id': user.id, 'model_id': self.env['ir.model']._get('res.partner').id,
            'method_ids': [(6, 0, methods.filtered(lambda m: m.name == 'create').ids)], 'forever': True,
        })
        self.authenticate('uam_http_locked', 'uam_http_locked')
        with self.assertRaises(JsonRpcException) as cm:
            self.make_jsonrpc_request('/web/dataset/call_kw/res.partner/create', {
                'model': 'res.partner', 'method': 'create', 'args': [{'name': 'X'}], 'kwargs': {}})
        self.assertIn('UserError', str(cm.exception))
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'X')]))
