import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import format_datetime


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
        self.assertEqual(key('web_unlink', [[3]]), 'unlink')
        self.assertEqual(key('action_archive', [[3]]), 'action_archive')
        self.assertEqual(key('copy', [[3]]), 'create')
        self.assertEqual(key('name_create', ['x']), 'create')
        self.assertEqual(key('load', [[], []]), 'create')
        self.assertEqual(key('web_resequence', [[3]]), 'write')

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

    def test_past_date_rejected_at_create(self):
        with self.assertRaises(ValidationError):
            self._lock(['create'], forever=False, date_until=fields.Datetime.now() - timedelta(minutes=1))

    def test_message_uses_user_tz(self):
        self.user.tz = 'Asia/Kolkata'
        until = fields.Datetime.now() + timedelta(hours=2)
        self._lock(['create'], forever=False, date_until=until)
        with self.assertRaises(UserError) as cm:
            self.Lock.with_user(self.user)._check('res.partner', 'create', [{}])
        self.assertIn(format_datetime(self.env, until, tz='Asia/Kolkata'), str(cm.exception))
        self.assertNotIn(fields.Datetime.to_string(until), str(cm.exception))

    def test_display_name(self):
        self.assertEqual(self._lock(['create']).display_name, f'{self.user.name} – {self.partner_model.name}')
        self.assertEqual(self.Lock.new({}).display_name, 'New Lock')

    def test_needs_date_or_forever(self):
        with self.assertRaises(ValidationError):
            self._lock(['create'], forever=False)

    def _group_lock(self, group, names, **vals):
        return self.Lock.create({
            'group_id': group.id, 'model_id': self.partner_model.id,
            'method_ids': [(6, 0, self.methods.filtered(lambda m: m.name in names).ids)],
            'forever': True, **vals,
        })

    def test_group_lock_follows_membership(self):
        group = self.env['res.groups'].create({'name': 'UAM lock group'})
        self._group_lock(group, ['create'])
        self.Lock.with_user(self.user)._check('res.partner', 'create', [{}])  # not a member yet
        self.user.write({'group_ids': [(4, group.id)]})
        with self.assertRaises(UserError):
            self.Lock.with_user(self.user)._check('res.partner', 'create', [{}])
        self.user.write({'group_ids': [(3, group.id)]})
        self.Lock.with_user(self.user)._check('res.partner', 'create', [{}])

    def test_user_or_group_required(self):
        group = self.env['res.groups'].create({'name': 'UAM both'})
        with self.assertRaises(ValidationError):
            self.Lock.create({'model_id': self.partner_model.id, 'forever': True,
                              'method_ids': [(6, 0, self.methods[:1].ids)]})
        with self.assertRaises(ValidationError):
            self.Lock.create({'user_id': self.user.id, 'group_id': group.id, 'model_id': self.partner_model.id,
                              'forever': True, 'method_ids': [(6, 0, self.methods[:1].ids)]})

    def test_no_lock_on_lock_screen(self):
        lock_model = self.env['ir.model']._get('uam.access.lock')
        methods = self.env['uam.lock.method']._sync_for_model('uam.access.lock')
        with self.assertRaises(ValidationError):
            self.Lock.create({'user_id': self.user.id, 'model_id': lock_model.id, 'forever': True,
                              'method_ids': [(6, 0, methods[:1].ids)]})

    def test_no_admin_lockout_on_admin_models(self):
        admin = self.env.ref('base.user_admin')
        users_model = self.env['ir.model']._get('res.users')
        methods = self.env['uam.lock.method']._sync_for_model('res.users')
        with self.assertRaises(ValidationError):
            self.Lock.create({'user_id': admin.id, 'model_id': users_model.id, 'forever': True,
                              'method_ids': [(6, 0, methods.filtered(lambda m: m.name == 'write').ids)]})
        with self.assertRaises(ValidationError):
            self.Lock.create({'group_id': self.env.ref('base.group_system').id, 'model_id': users_model.id,
                              'forever': True, 'method_ids': [(6, 0, methods.filtered(lambda m: m.name == 'write').ids)]})

    def test_no_admin_lockout_via_write(self):
        users_model = self.env['ir.model']._get('res.users')
        methods = self.env['uam.lock.method']._sync_for_model('res.users')
        lock = self.Lock.create({'user_id': self.user.id, 'model_id': users_model.id, 'forever': True,
                                 'method_ids': [(6, 0, methods.filtered(lambda m: m.name == 'write').ids)]})
        with self.assertRaises(ValidationError):
            lock.write({'group_id': self.env.ref('base.group_system').id, 'user_id': False})

    def test_state_unlock_extend(self):
        lock = self._lock(['create'], forever=False, date_until=fields.Datetime.now() + timedelta(hours=1))
        self.assertEqual(lock.lock_state, 'active')
        before = lock.date_until
        lock.action_extend_day()
        self.assertEqual(lock.date_until, before + timedelta(days=1))
        lock.action_unlock()
        self.assertFalse(lock.active)
        self.assertEqual(lock.lock_state, 'expired')
        self.assertEqual(self._lock(['write']).lock_state, 'forever')


@tagged('post_install', '-at_install')
class TestAccessLockHttp(HttpCase):

    def _locked_user(self, name):
        """Return a partner-manager user locked on res.partner for the given method name."""
        user = new_test_user(self.env, login='uam_http_locked', password='uam_http_locked',
                             groups='base.group_user,base.group_partner_manager')
        model = self.env['ir.model']._get('res.partner')
        methods = self.env['uam.lock.method']._sync_for_model('res.partner')
        method = methods.filtered(lambda m: m.name == name) or self.env['uam.lock.method'].create(
            {'model_id': model.id, 'name': name, 'label': name.title()})
        self.env['uam.access.lock'].create({
            'user_id': user.id, 'model_id': model.id, 'method_ids': [(6, 0, method.ids)], 'forever': True,
        })
        return user

    def test_call_kw_blocked(self):
        self._locked_user('create')
        self.authenticate('uam_http_locked', 'uam_http_locked')
        with self.assertRaises(JsonRpcException) as cm:
            self.make_jsonrpc_request('/web/dataset/call_kw/res.partner/create', {
                'model': 'res.partner', 'method': 'create', 'args': [{'name': 'X'}], 'kwargs': {}})
        self.assertIn('UserError', str(cm.exception))
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'X')]))

    def test_call_button_blocked(self):
        self._locked_user('action_archive')
        partner = self.env['res.partner'].create({'name': 'UAM button target'})
        self.authenticate('uam_http_locked', 'uam_http_locked')
        with self.assertRaises(JsonRpcException) as cm:
            self.make_jsonrpc_request('/web/dataset/call_button/res.partner/action_archive', {
                'model': 'res.partner', 'method': 'action_archive', 'args': [[partner.id]], 'kwargs': {}})
        self.assertIn('UserError', str(cm.exception))
        partner.invalidate_recordset()
        self.assertTrue(partner.active)

    def test_json2_blocked(self):
        user = self._locked_user('create')
        key = self.env['res.users.apikeys'].with_user(user).sudo()._generate('rpc', 'uam test', None)
        response = self.url_open('/json/2/res.partner/create', headers={'Authorization': f'Bearer {key}'},
                                 json={'vals_list': [{'name': 'Y'}]})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Y')]))

    def test_print_blocked(self):
        self._locked_user('print')
        self.env['ir.actions.report'].create({
            'name': 'UAM test report', 'model': 'res.partner', 'report_type': 'qweb-pdf',
            'report_name': 'uam_test.report_partner',
        })
        partner = self.env['res.partner'].create({'name': 'UAM print target'})
        logs_before = self.env['uam.print.log'].search_count([])
        self.authenticate('uam_http_locked', 'uam_http_locked')
        response = self.url_open('/report/download', data={
            'data': json.dumps([f'/report/pdf/uam_test.report_partner/{partner.id}', 'qweb-pdf']),
            'csrf_token': self.csrf_token(),
        })
        # like web's own report errors: 200 + text/html JSON error body, which the client's download() shows
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertNotIn('Content-Disposition', response.headers)
        self.assertIn('Locked by administrator', response.text)
        self.assertEqual(self.env['uam.print.log'].search_count([]), logs_before)

    def test_report_get_blocked(self):
        self._locked_user('print')
        self.env['ir.actions.report'].create({
            'name': 'UAM test report', 'model': 'res.partner', 'report_type': 'qweb-pdf',
            'report_name': 'uam_test.report_partner',
        })
        partner = self.env['res.partner'].create({'name': 'UAM direct print'})
        self.authenticate('uam_http_locked', 'uam_http_locked')
        response = self.url_open(f'/report/pdf/uam_test.report_partner/{partner.id}')
        self.assertNotEqual(response.headers.get('Content-Type'), 'application/pdf')
        self.assertTrue('Locked by administrator' in response.text or 'UserError' in response.text, response.text[:300])
