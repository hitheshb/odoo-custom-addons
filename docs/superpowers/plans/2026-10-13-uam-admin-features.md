# UAM Admin Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a home-page admin dashboard, Print Log, Access Lock, read-only Access Simulation and a configurable stale-login threshold to `user_access_management`.

**Architecture:** Thin controller overrides (`DataSet.call_kw/call_button`, `ReportController.report_download`, JSON-2 RPC) delegate to model methods (`uam.access.lock._check`, `uam.print.log._record`) so all logic is unit-testable. A small JS service reports the current page to `res.users.uam_track`. An OWL client action renders `uam.dashboard.get_data(date)`.

**Tech Stack:** Odoo 20 (Python 3.12, OWL 3 with `proxy`/`useProps`), PostgreSQL, `ir.access.csv` (Odoo 20 `operation` column).

**Spec:** `docs/superpowers/specs/2026-10-13-uam-admin-features-design.md`

## Global Constraints

- Module: `user_access_management`, Odoo 20. All new models visible to `base.group_system` only.
- Security file is `security/ir.access.csv` with columns `id,name,model_id,group_id/id,operation,domain`; `operation` is a subset of `crud` (e.g. `r`, `crud`).
- Unique constraints use `models.Constraint('UNIQUE(...)', 'message')` (not `_sql_constraints`).
- Translations: `self.env._('...')` (existing module idiom).
- JS: OWL 3 — `props = useProps(...)`, reactive state via `proxy({...})`, imports from `@odoo/owl`.
- Stale default: 3 days, config parameter key `user_access_management.stale_login_days`.
- Print copy counting: per document, global; `copy_no` 0 = "Original", N = "Copy-N". Document key = report + sorted comma-joined ids.
- Re-download serves the exact stored bytes (`ir.attachment`), no watermark.
- Lock methods: `create`, `write`, `unlink`, `print`, plus form-view `button[@type='object']` names.
- Simulation is read-only.
- Test runner: `scripts/test_module.sh user_access_management` from `/home/hithesh/odoo20/custom-addons` (run **unsandboxed**; exit code = pass/fail). UI check: Playwright on `http://localhost:8070`.

## Review Focus

1. Printing several records at once (ids `5,3` vs `3,5`) → same document, so the second print is Copy-1. Pinned in Task 2 (`test_multi_record_order_independent`).
2. A lock that expired but has not been archived by the cron yet → must NOT block. Pinned in Task 3 (`test_expired_lock_not_enforced`).
3. A lock on user A must not block user B on the same model/method. Pinned in Task 3 (`test_other_user_not_blocked`).
4. Form save of a new record goes through `web_save` with empty ids → must count as Create, not Edit. Pinned in Task 3 (`test_web_save_maps_to_create_or_write`).
5. Page tracking on a client action (no model, e.g. the dashboard itself) → updates current page, writes no usage row, no error. Pinned in Task 4 (`test_track_without_model`).

## Preconditions

- [ ] **P1:** The module has uncommitted user work (`git status` shows `M models/res_users.py`, `views/*.xml`, untracked `models/temp_access.py`, etc.). Ask the user to commit or confirm it first — task commits below `git add` these same files and would otherwise sweep that work into feature commits.
- [ ] **P2:** Odoo server on :8070 uses db `odoo20`; Postgres running (`pg_isready`).

## File Structure

| File | Responsibility |
|---|---|
| `models/res_config_settings.py` (new) | `uam_stale_login_days` setting |
| `models/res_users.py` (modify) | stale limit/search, `uam_current_page`, `uam_last_seen`, `uam_track`, home-action helper |
| `models/print_log.py` (new) | `uam.print.log` + `_record()` |
| `models/access_lock.py` (new) | `uam.access.lock`, `uam.lock.method`, `_check()`, `_sync_for_model()`, cron |
| `models/model_usage.py` (new) | `uam.model.usage` + `_bump()` SQL upsert |
| `models/access_simulation.py` (new) | `uam.access.simulation` read-only wizard |
| `models/dashboard.py` (new) | `uam.dashboard` AbstractModel: `get_data()`, `open_tile()` |
| `controllers/__init__.py`, `controllers/main.py` (new) | DataSet / Report / JSON-2 overrides |
| `static/src/page_tracker.js` (new) | reports current page |
| `static/src/dashboard/dashboard.js`, `.xml` (new) | dashboard client action |
| `views/*.xml` (new per feature) | list/form/actions |
| `data/uam_data.xml` (new) | lock cron + home-action function |
| `tests/test_*.py` (new, one per feature) | tests |

---

### Task 1: Configurable stale-login days

**Files:**
- Create: `models/res_config_settings.py`, `views/res_config_settings_views.xml`, `tests/__init__.py`, `tests/test_stale_login.py`
- Modify: `models/__init__.py`, `models/res_users.py:14,26-29`, `views/user_views.xml:66-67`, `views/menus.xml`, `__manifest__.py`

**Interfaces:**
- Produces: `res.users._uam_stale_limit() -> datetime`; `uam_login_stale` searchable (`[('uam_login_stale', '=', True)]`). Used by Task 6 dashboard.

- [ ] **Step 1: Write the failing test** — `tests/__init__.py`:

```python
from . import test_stale_login
```

`tests/test_stale_login.py`:

```python
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

        param.set_param('user_access_management.stale_login_days', 3)
        self.assertTrue(user.uam_login_stale)
        self.assertEqual(self.env['res.users'].search(stale), user)

        param.set_param('user_access_management.stale_login_days', 7)
        user.invalidate_recordset(['uam_login_stale'])
        self.assertFalse(user.uam_login_stale)
        self.assertFalse(self.env['res.users'].search(stale))
        self.assertEqual(self.env['res.users'].search([('uam_login_stale', '=', False), ('id', '=', user.id)]), user)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/hithesh/odoo20/custom-addons && scripts/test_module.sh user_access_management`
Expected: FAIL with an error that `res.users.uam_login_stale` cannot be searched (non-stored, no search method). Odoo discovers `tests/` on its own; do not import it from the module `__init__.py`.

- [ ] **Step 3: Implement**

`models/res_config_settings.py`:

```python
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    uam_stale_login_days = fields.Integer(
        string='Stale Login After (days)',
        config_parameter='user_access_management.stale_login_days',
        default=3,
    )
```

`models/__init__.py` — append `from . import res_config_settings`.

`models/res_users.py` — replace the field line and compute:

```python
    uam_login_stale = fields.Boolean(compute='_compute_uam_login_stale', search='_search_uam_login_stale')
```

```python
    def _uam_stale_limit(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param('user_access_management.stale_login_days', 3))
        return fields.Datetime.now() - timedelta(days=days)

    def _compute_uam_login_stale(self):
        limit = self._uam_stale_limit()
        for user in self:
            user.uam_login_stale = not user.login_date or user.login_date < limit

    def _search_uam_login_stale(self, operator, value):
        if operator in ('in', 'not in'):
            positive = (True in value) == (operator == 'in')
        elif operator in ('=', '!='):
            positive = bool(value) == (operator == '=')
        else:
            return NotImplemented
        domain = ['|', ('login_date', '=', False), ('login_date', '<', self._uam_stale_limit())]
        return domain if positive else ['!', *domain]
```

`views/user_views.xml` lines 66-67 → 

```xml
                <filter name="stale" string="Stale Login" domain="[('uam_login_stale', '=', True)]"/>
```

`views/res_config_settings_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="res_config_settings_view_form_uam" model="ir.ui.view">
        <field name="name">res.config.settings.view.form.inherit.uam</field>
        <field name="model">res.config.settings</field>
        <field name="priority" eval="40"/>
        <field name="inherit_id" ref="base.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//form" position="inside">
                <app data-string="User Access" string="User Access" name="user_access_management" groups="base.group_system">
                    <block title="Logins">
                        <setting help="Users who have not logged in for this many days are flagged as stale">
                            <field name="uam_stale_login_days"/>
                        </setting>
                    </block>
                </app>
            </xpath>
        </field>
    </record>
    <record id="uam_settings_action" model="ir.actions.act_window">
        <field name="name">Settings</field>
        <field name="res_model">res.config.settings</field>
        <field name="view_mode">form</field>
        <field name="target">inline</field>
        <field name="context">{'module': 'user_access_management'}</field>
    </record>
</odoo>
```

`views/menus.xml` — add:

```xml
    <menuitem id="menu_uam_config" name="Configuration" parent="menu_uam_root" sequence="90"/>
    <menuitem id="menu_uam_settings" name="Settings" parent="menu_uam_config" action="uam_settings_action" sequence="10"/>
```

`__manifest__.py` `data` — add `'views/res_config_settings_views.xml'` before `'views/menus.xml'`.

- [ ] **Step 4: Run tests** — same command. Expected: exit 0, no `FAIL`/`ERROR` lines.

- [ ] **Step 5: Commit**

```bash
git add user_access_management/models/res_config_settings.py user_access_management/models/__init__.py user_access_management/models/res_users.py user_access_management/views/user_views.xml user_access_management/views/res_config_settings_views.xml user_access_management/views/menus.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): configurable stale-login days"
```

---

### Task 2: Print Log

**Files:**
- Create: `models/print_log.py`, `controllers/__init__.py`, `controllers/main.py`, `views/print_log_views.xml`, `tests/test_print_log.py`
- Modify: `__init__.py`, `models/__init__.py`, `security/ir.access.csv`, `views/menus.xml`, `__manifest__.py`, `tests/__init__.py`

**Interfaces:**
- Produces: `uam.print.log._record(report: ir.actions.report, res_ids: list[int], content: bytes) -> uam.print.log`; fields `user_id, report_id, model, res_ids, record_name, copy_no, label, attachment_id, create_date`; `action_download()`. `controllers/main.py` with `_parse_report_url(url, type_) -> (report|None, list[int])` reused by Task 3.

- [ ] **Step 1: Write the failing test** — `tests/test_print_log.py` (and add `from . import test_print_log` to `tests/__init__.py`):

```python
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrintLog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env['ir.actions.report'].search([('report_type', '=', 'qweb-pdf')], limit=1)
        cls.Log = cls.env['uam.print.log'].sudo()

    def test_original_then_copies(self):
        first = self.Log._record(self.report, [1], b'%PDF-a')
        second = self.Log._record(self.report, [1], b'%PDF-b')
        third = self.Log._record(self.report, [1], b'%PDF-c')
        self.assertEqual([first.label, second.label, third.label], ['Original', 'Copy-1', 'Copy-2'])
        self.assertEqual(second.attachment_id.raw, b'%PDF-b')

    def test_multi_record_order_independent(self):
        self.Log._record(self.report, [5, 3], b'%PDF')
        again = self.Log._record(self.report, [3, 5], b'%PDF')
        self.assertEqual(again.res_ids, '3,5')
        self.assertEqual(again.copy_no, 1)

    def test_download_action_points_to_attachment(self):
        log = self.Log._record(self.report, [7], b'%PDF')
        action = log.action_download()
        self.assertEqual(action['url'], f'/web/content/{log.attachment_id.id}?download=true')
```

- [ ] **Step 2: Run test** — `scripts/test_module.sh user_access_management`. Expected: FAIL `KeyError: 'uam.print.log'`.

- [ ] **Step 3: Implement**

`models/print_log.py`:

```python
from psycopg2 import IntegrityError

from odoo import api, fields, models


class UamPrintLog(models.Model):
    _name = 'uam.print.log'
    _description = 'Print Log'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True, default=lambda self: self.env.uid)
    report_id = fields.Many2one('ir.actions.report', required=True, readonly=True, ondelete='cascade', index=True)
    model = fields.Char(readonly=True)
    res_ids = fields.Char('Record IDs', required=True, readonly=True, index=True)
    record_name = fields.Char('Document', readonly=True)
    copy_no = fields.Integer(readonly=True)
    label = fields.Char(compute='_compute_label')
    attachment_id = fields.Many2one('ir.attachment', readonly=True)

    _uniq_copy = models.Constraint('UNIQUE(report_id, res_ids, copy_no)', 'This copy number already exists.')

    @api.depends('copy_no')
    def _compute_label(self):
        for log in self:
            log.label = f'Copy-{log.copy_no}' if log.copy_no else 'Original'

    @api.model
    def _record(self, report, res_ids, content):
        key = ','.join(map(str, sorted(set(res_ids))))
        records = self.env[report.model].browse(sorted(set(res_ids))).exists()
        vals = {
            'report_id': report.id, 'model': report.model, 'res_ids': key,
            'record_name': ', '.join(records.mapped('display_name'))[:250],
        }
        for attempt in range(2):
            vals['copy_no'] = self.search_count([('report_id', '=', report.id), ('res_ids', '=', key)])
            try:
                with self.env.cr.savepoint():
                    log = self.create(vals)
                break
            except IntegrityError:
                if attempt:
                    raise
        log.attachment_id = self.env['ir.attachment'].create({
            'name': f'{report.name} - {log.record_name or key} ({log.label}).pdf',
            'raw': content, 'mimetype': 'application/pdf',
            'res_model': self._name, 'res_id': log.id,
        })
        return log

    def action_download(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{self.attachment_id.id}?download=true',
                'target': 'self'}
```

`models/__init__.py` — append `from . import print_log`.
`__init__.py`:

```python
from . import controllers
from . import models
```

`controllers/__init__.py`:

```python
from . import main
```

`controllers/main.py`:

```python
import json

from odoo.http import request, route

from odoo.addons.web.controllers.report import ReportController


def _parse_report_url(url, type_):
    """Return (report, ids) for a '/report/pdf/<name>/<ids>' download, else (None, [])."""
    if not type_.startswith('qweb-pdf') or '/report/pdf/' not in url:
        return None, []
    name = url.split('/report/pdf/')[1].split('?')[0]
    if '/' not in name:
        return None, []
    name, docids = name.split('/', 1)
    report = request.env['ir.actions.report']._get_report_from_name(name)
    return report, [int(i) for i in docids.split(',') if i.isdigit()]


class UamReportController(ReportController):

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        url, type_ = json.loads(data)[:2]
        report, ids = _parse_report_url(url, type_)
        response = super().report_download(data, context=context, token=token, readonly=readonly)
        if report and ids and response.status_code == 200 and response.mimetype == 'application/pdf':
            request.env['uam.print.log'].sudo()._record(report, ids, response.get_data())
        return response
```

`security/ir.access.csv` — append:

```
access_uam_print_log_admin,uam.print.log admin,uam.print.log,base.group_system,r,
```

`views/print_log_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="print_log_view_list" model="ir.ui.view">
        <field name="name">uam.print.log.list</field>
        <field name="model">uam.print.log</field>
        <field name="arch" type="xml">
            <list create="0" edit="0" delete="0">
                <field name="create_date" string="Downloaded"/>
                <field name="user_id" widget="many2one_avatar_user"/>
                <field name="report_id"/>
                <field name="record_name"/>
                <field name="label" widget="badge" decoration-success="copy_no == 0" decoration-warning="copy_no > 0"/>
                <field name="copy_no" column_invisible="1"/>
                <button name="action_download" type="object" icon="fa-download" title="Download this copy"/>
            </list>
        </field>
    </record>
    <record id="print_log_view_search" model="ir.ui.view">
        <field name="name">uam.print.log.search</field>
        <field name="model">uam.print.log</field>
        <field name="arch" type="xml">
            <search>
                <field name="record_name"/>
                <field name="user_id"/>
                <field name="report_id"/>
                <filter name="original" string="Originals" domain="[('copy_no', '=', 0)]"/>
                <filter name="copies" string="Copies" domain="[('copy_no', '>', 0)]"/>
                <separator/>
                <filter name="today" string="Today" domain="[('create_date', '>=', context_today().strftime('%Y-%m-%d'))]"/>
                <group>
                    <filter name="by_user" string="User" context="{'group_by': 'user_id'}"/>
                    <filter name="by_report" string="Report" context="{'group_by': 'report_id'}"/>
                </group>
            </search>
        </field>
    </record>
    <record id="print_log_action" model="ir.actions.act_window">
        <field name="name">Print Log</field>
        <field name="res_model">uam.print.log</field>
        <field name="view_mode">list</field>
    </record>
</odoo>
```

`views/menus.xml` — add `<menuitem id="menu_uam_print_log" name="Print Log" parent="menu_uam_logs" action="print_log_action" sequence="30"/>`.
`__manifest__.py` — add `'views/print_log_views.xml'` before `'views/menus.xml'`.

- [ ] **Step 4: Run tests** — expected exit 0.

- [ ] **Step 5: Manual check** — restart Odoo on :8070, open any record with a Print menu (e.g. a contact/quotation), print the PDF twice; open User Access › Logs › Print Log: rows "Original", "Copy-1"; click ⬇ on Copy-1 → same PDF downloads.

- [ ] **Step 6: Commit**

```bash
git add user_access_management/__init__.py user_access_management/controllers user_access_management/models/print_log.py user_access_management/models/__init__.py user_access_management/security/ir.access.csv user_access_management/views/print_log_views.xml user_access_management/views/menus.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): print log with original/copy numbering and re-download"
```

---

### Task 3: Access Lock

**Files:**
- Create: `models/access_lock.py`, `views/access_lock_views.xml`, `data/uam_data.xml`, `tests/test_access_lock.py`
- Modify: `controllers/main.py`, `models/__init__.py`, `security/ir.access.csv`, `views/menus.xml`, `__manifest__.py` (add `'rpc'` to depends, add files), `tests/__init__.py`

**Interfaces:**
- Consumes: `_parse_report_url` from Task 2.
- Produces: `uam.access.lock._check(model: str, method: str, args: list) -> None` (raises `UserError`); `uam.access.lock._method_key(method, args) -> str`; `uam.lock.method._sync_for_model(model_name: str) -> uam.lock.method`. Task 6 counts `uam.access.lock` with `active=True`.

- [ ] **Step 1: Write the failing test** — `tests/test_access_lock.py` (add import to `tests/__init__.py`):

```python
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


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
        with self.assertRaises(Exception):
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
        with self.assertRaisesRegex(Exception, 'Locked by administrator'):
            self.make_jsonrpc_request('/web/dataset/call_kw/res.partner/create', {
                'model': 'res.partner', 'method': 'create', 'args': [{'name': 'X'}], 'kwargs': {}})
```

- [ ] **Step 2: Run test** — expected FAIL `KeyError: 'uam.access.lock'`.

- [ ] **Step 3: Implement models** — `models/access_lock.py`:

```python
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

FIXED_METHODS = [('create', 'Create'), ('write', 'Edit'), ('unlink', 'Delete'), ('print', 'Print')]


class UamLockMethod(models.Model):
    _name = 'uam.lock.method'
    _description = 'Lockable Method'
    _order = 'sequence, id'

    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', index=True)
    name = fields.Char('Technical Name', required=True)
    label = fields.Char(required=True)
    sequence = fields.Integer(default=10)

    _uniq_method = models.Constraint('UNIQUE(model_id, name)', 'Method already listed for this model.')

    @api.depends('label', 'name')
    def _compute_display_name(self):
        for m in self:
            m.display_name = f'{m.label} ({m.name})' if m.label.lower() != m.name else m.label

    @api.model
    def _sync_for_model(self, model_name):
        model = self.env['ir.model']._get(model_name)
        found = list(FIXED_METHODS)
        arch = self.env[model_name].sudo().get_view(view_type='form')['arch']
        for btn in etree.fromstring(arch).iter('button'):
            name = btn.get('name')
            if btn.get('type') == 'object' and name and name not in dict(found):
                found.append((name, btn.get('string') or name))
        existing = self.search([('model_id', '=', model.id)])
        known = set(existing.mapped('name'))
        self.create([{'model_id': model.id, 'name': n, 'label': l, 'sequence': i}
                     for i, (n, l) in enumerate(found) if n not in known])
        return self.search([('model_id', '=', model.id)])


class UamAccessLock(models.Model):
    _name = 'uam.access.lock'
    _description = 'Access Lock'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', index=True)
    method_ids = fields.Many2many('uam.lock.method', string='Methods', required=True,
                                  domain="[('model_id', '=', model_id)]")
    date_until = fields.Datetime('Locked Until')
    forever = fields.Boolean()
    active = fields.Boolean(default=True)
    note = fields.Char()

    @api.constrains('forever', 'date_until')
    def _check_until(self):
        for lock in self:
            if not lock.forever and not lock.date_until:
                raise ValidationError(self.env._("Set 'Locked Until' or tick 'Forever'."))

    @api.onchange('model_id')
    def _onchange_model_id(self):
        self.method_ids = False
        if self.model_id:
            self.env['uam.lock.method'].sudo()._sync_for_model(self.model_id.model)

    @api.model
    def _method_key(self, method, args):
        if method in ('web_save', 'web_save_multi'):
            return 'write' if args and args[0] else 'create'
        return method

    @api.model
    def _check(self, model, method, args):
        key = self._method_key(method, args)
        lock = self.sudo().search([
            ('user_id', '=', self.env.uid), ('model_id.model', '=', model), ('method_ids.name', '=', key),
            '|', ('forever', '=', True), ('date_until', '>', fields.Datetime.now()),
        ], limit=1)
        if lock:
            label = lock.method_ids.filtered(lambda m: m.name == key)[:1].label or key
            until = self.env._('forever') if lock.forever else fields.Datetime.to_string(lock.date_until)
            raise UserError(self.env._('Locked by administrator until %(until)s: %(label)s on %(model)s',
                                       until=until, label=label, model=lock.model_id.name))

    @api.model
    def _cron_archive_expired(self):
        self.search([('forever', '=', False), ('date_until', '<=', fields.Datetime.now())]).active = False
```

`models/__init__.py` — append `from . import access_lock`.

- [ ] **Step 4: Implement controller checks** — in `controllers/main.py`, add these imports at the top (next to the existing ones):

```python
from odoo import http
from odoo.addons.rpc.controllers.json2 import WebJson2Controller
from odoo.addons.web.controllers.dataset import DataSet
```

then append these classes at the bottom:

```python
class UamDataSet(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        request.env['uam.access.lock']._check(model, method, args)
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        request.env['uam.access.lock']._check(model, method, args)
        return super().call_button(model, method, args, kwargs, path=path)


class UamJson2(WebJson2Controller):

    @http.route()
    def web_json_2_rpc(self, __model__, __method__, ids=(), context=None, **kwargs):
        request.env['uam.access.lock']._check(__model__, __method__, [list(ids)])
        if context is None:
            return super().web_json_2_rpc(__model__, __method__, ids=ids, **kwargs)
        return super().web_json_2_rpc(__model__, __method__, ids=ids, context=context, **kwargs)
```

and in `UamReportController.report_download`, right after `report, ids = _parse_report_url(url, type_)`:

```python
        if report:
            request.env['uam.access.lock']._check(report.model, 'print', [ids])
```

`__manifest__.py` — `'depends': ['base', 'mail', 'rpc'],` (`rpc` is auto-install on base, so this adds nothing new to the db).

- [ ] **Step 5: Views, security, cron**

`security/ir.access.csv` — append:

```
access_uam_access_lock_admin,uam.access.lock admin,uam.access.lock,base.group_system,crud,
access_uam_lock_method_admin,uam.lock.method admin,uam.lock.method,base.group_system,crud,
```

`views/access_lock_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="access_lock_view_list" model="ir.ui.view">
        <field name="name">uam.access.lock.list</field>
        <field name="model">uam.access.lock</field>
        <field name="arch" type="xml">
            <list>
                <field name="user_id" widget="many2one_avatar_user"/>
                <field name="model_id"/>
                <field name="method_ids" widget="many2many_tags"/>
                <field name="forever"/>
                <field name="date_until" widget="relative_date" invisible="forever"/>
                <field name="note" optional="hide"/>
            </list>
        </field>
    </record>
    <record id="access_lock_view_form" model="ir.ui.view">
        <field name="name">uam.access.lock.form</field>
        <field name="model">uam.access.lock</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-secondary" invisible="active"/>
                    <field name="active" invisible="1"/>
                    <group>
                        <group>
                            <field name="user_id"/>
                            <field name="model_id" options="{'no_create': True}"/>
                        </group>
                        <group>
                            <field name="forever"/>
                            <field name="date_until" invisible="forever" required="not forever"/>
                            <field name="note"/>
                        </group>
                    </group>
                    <separator string="Methods to block" invisible="not model_id"/>
                    <field name="method_ids" widget="many2many_checkboxes" invisible="not model_id"/>
                </sheet>
            </form>
        </field>
    </record>
    <record id="access_lock_view_search" model="ir.ui.view">
        <field name="name">uam.access.lock.search</field>
        <field name="model">uam.access.lock</field>
        <field name="arch" type="xml">
            <search>
                <field name="user_id"/>
                <field name="model_id"/>
                <filter name="archived" string="Archived" domain="[('active', '=', False)]"/>
            </search>
        </field>
    </record>
    <record id="access_lock_action" model="ir.actions.act_window">
        <field name="name">Access Lock</field>
        <field name="res_model">uam.access.lock</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

`data/uam_data.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="cron_uam_access_lock_archive" model="ir.cron">
        <field name="name">User Access: archive expired access locks</field>
        <field name="model_id" ref="model_uam_access_lock"/>
        <field name="state">code</field>
        <field name="code">model._cron_archive_expired()</field>
        <field name="user_id" ref="base.user_root"/>
        <field name="interval_number">1</field>
        <field name="interval_type">hours</field>
    </record>
</odoo>
```

`views/menus.xml` — add `<menuitem id="menu_uam_access_lock" name="Access Lock" parent="menu_uam_privileges" action="access_lock_action" sequence="60"/>`.
`__manifest__.py` `data` — add `'views/access_lock_views.xml'` before menus, `'data/uam_data.xml'` after `'data/ir_cron.xml'`.

- [ ] **Step 6: Run tests** — expected exit 0. If `test_call_kw_blocked` fails because `make_jsonrpc_request` returns the error instead of raising, change it to assert `'Locked by administrator' in str(response)` — check `odoo/tests/common.py:3029` for its behaviour first.

- [ ] **Step 7: Manual check** — on :8070 create a lock for a demo user on `res.partner` → tick Create, Forever. Confirm the checkbox list fills after picking the model. Log in as that user, try New contact → Save: error "Locked by administrator until forever: Create on Contact". Editing an existing contact still works.

- [ ] **Step 8: Commit**

```bash
git add user_access_management/models/access_lock.py user_access_management/models/__init__.py user_access_management/controllers/main.py user_access_management/security/ir.access.csv user_access_management/views/access_lock_views.xml user_access_management/views/menus.xml user_access_management/data/uam_data.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): access lock blocks chosen methods per user until a date"
```

---

### Task 4: Page tracking and model usage

**Files:**
- Create: `models/model_usage.py`, `views/model_usage_views.xml`, `static/src/page_tracker.js`, `tests/test_tracking.py`
- Modify: `models/res_users.py`, `models/__init__.py`, `security/ir.access.csv`, `views/menus.xml`, `__manifest__.py`, `tests/__init__.py`

**Interfaces:**
- Produces: `res.users.uam_track(model: str|False, action: int|str|False, page: str) -> True` (`@api.model`, acts on current user); fields `res.users.uam_current_page`, `res.users.uam_last_seen`; `uam.model.usage` fields `user_id, model, model_name, date, view_count, first_seen, last_seen`; `uam.model.usage._bump(user_id: int, model: str)`. Task 6 reads all of these.

- [ ] **Step 1: Write the failing test** — `tests/test_tracking.py` (add import):

```python
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
```

- [ ] **Step 2: Run test** — expected FAIL `AttributeError: ... uam_track`.

- [ ] **Step 3: Implement** — `models/model_usage.py`:

```python
from odoo import api, fields, models
from odoo.tools import SQL


class UamModelUsage(models.Model):
    _name = 'uam.model.usage'
    _description = 'Model Usage per Day'
    _order = 'date desc, last_seen desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, ondelete='cascade', index=True)
    model = fields.Char(required=True, readonly=True)
    model_name = fields.Char('Model', compute='_compute_model_name')
    date = fields.Date(required=True, readonly=True, index=True)
    view_count = fields.Integer('Views', readonly=True)
    first_seen = fields.Datetime(readonly=True)
    last_seen = fields.Datetime(readonly=True)

    _uniq_day = models.Constraint('UNIQUE(user_id, model, date)', 'One usage row per user, model and day.')

    @api.depends('model')
    def _compute_model_name(self):
        names = {m.model: m.name for m in self.env['ir.model'].sudo().search([('model', 'in', self.mapped('model'))])}
        for row in self:
            row.model_name = names.get(row.model, row.model)

    @api.model
    def _bump(self, user_id, model):
        now = fields.Datetime.now()
        self.env.cr.execute(SQL("""
            INSERT INTO uam_model_usage (user_id, model, date, view_count, first_seen, last_seen,
                                         create_uid, write_uid, create_date, write_date)
            VALUES (%(u)s, %(m)s, %(d)s, 1, %(n)s, %(n)s, %(u)s, %(u)s, %(n)s, %(n)s)
            ON CONFLICT (user_id, model, date)
            DO UPDATE SET view_count = uam_model_usage.view_count + 1, last_seen = EXCLUDED.last_seen
        """, u=user_id, m=model, d=fields.Date.context_today(self), n=now))
```

`models/res_users.py` — add fields and methods (add `from odoo.tools import SQL` import):

```python
    uam_current_page = fields.Char('Current Page', readonly=True)
    uam_last_seen = fields.Datetime('Last Seen', readonly=True)

    @api.model
    def uam_track(self, model, action, page):
        if not model and action:
            acts = self.env['ir.actions.act_window'].sudo()
            act = acts.browse(int(action)).exists() if str(action).isdigit() else acts.search([('path', '=', action)], limit=1)
            model = act.res_model
        self.env.cr.execute(SQL('UPDATE res_users SET uam_current_page = %s, uam_last_seen = %s WHERE id = %s',
                                (page or '')[:250], fields.Datetime.now(), self.env.uid))
        if model:
            self.env['uam.model.usage']._bump(self.env.uid, model)
        return True
```

`static/src/page_tracker.js`:

```javascript
import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const MIN_GAP_MS = 10 * 1000;

registry.category("services").add("uam_page_tracker", {
    dependencies: ["orm"],
    start(env, { orm }) {
        if (!user.isInternalUser) {
            return;
        }
        let lastKey = "";
        let lastAt = 0;
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => {
            const { model, action, resId } = router.current;
            const page = document.title.replace(/ - Odoo$/, "");
            const key = `${model}|${action}|${resId}|${page}`;
            if (key === lastKey && Date.now() - lastAt < MIN_GAP_MS) {
                return;
            }
            lastKey = key;
            lastAt = Date.now();
            orm.silent.call("res.users", "uam_track", [model || false, action || false, page]);
        });
    },
});
```

`security/ir.access.csv` — append `access_uam_model_usage_admin,uam.model.usage admin,uam.model.usage,base.group_system,r,`.

`views/model_usage_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="model_usage_view_list" model="ir.ui.view">
        <field name="name">uam.model.usage.list</field>
        <field name="model">uam.model.usage</field>
        <field name="arch" type="xml">
            <list create="0" edit="0" delete="0">
                <field name="date"/>
                <field name="user_id" widget="many2one_avatar_user"/>
                <field name="model_name"/>
                <field name="view_count" sum="Total"/>
                <field name="first_seen"/>
                <field name="last_seen"/>
            </list>
        </field>
    </record>
    <record id="model_usage_view_search" model="ir.ui.view">
        <field name="name">uam.model.usage.search</field>
        <field name="model">uam.model.usage</field>
        <field name="arch" type="xml">
            <search>
                <field name="user_id"/>
                <field name="model"/>
                <field name="date"/>
                <filter name="today" string="Today" domain="[('date', '=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="date_filter" string="Date" date="date"/>
                <group>
                    <filter name="by_user" string="User" context="{'group_by': 'user_id'}"/>
                    <filter name="by_date" string="Day" context="{'group_by': 'date:day'}"/>
                </group>
            </search>
        </field>
    </record>
    <record id="model_usage_action" model="ir.actions.act_window">
        <field name="name">Model Usage</field>
        <field name="res_model">uam.model.usage</field>
        <field name="view_mode">list</field>
        <field name="context">{'search_default_today': 1}</field>
    </record>
</odoo>
```

`views/menus.xml` — `<menuitem id="menu_uam_usage" name="Model Usage" parent="menu_uam_logs" action="model_usage_action" sequence="40"/>`.
`views/user_views.xml` — in the user form, next to `login_date` (around line 98), add `<field name="uam_current_page"/>` and `<field name="uam_last_seen" widget="relative_date"/>`.
`models/__init__.py` — append `from . import model_usage`. `__manifest__.py` — add `'views/model_usage_views.xml'` before menus (assets glob already picks up `page_tracker.js`).

- [ ] **Step 4: Run tests** — expected exit 0.

- [ ] **Step 5: Manual check** — on :8070 open Contacts, then a contact. Logs › Model Usage → today row `Contact` with Views ≥ 2; your user form shows Current Page. If no row appears, check the browser console: confirm `ACTION_MANAGER:UI-UPDATED` fires on `env.bus` in a service (it is triggered on the global bus in `web/static/src/webclient/actions/action_plugin.js:1090`). If it does not reach services, switch the listener to `routerBus` from `@web/core/browser/router` plus a `setInterval` check of `router.current` every 5 s.

- [ ] **Step 6: Commit**

```bash
git add user_access_management/models/model_usage.py user_access_management/models/res_users.py user_access_management/models/__init__.py user_access_management/static/src/page_tracker.js user_access_management/security/ir.access.csv user_access_management/views/model_usage_views.xml user_access_management/views/user_views.xml user_access_management/views/menus.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): track current page and per-day model usage"
```

---

### Task 5: Access Simulation (read-only)

**Files:**
- Create: `models/access_simulation.py`, `views/access_simulation_views.xml`, `tests/test_simulation.py`
- Modify: `models/__init__.py`, `security/ir.access.csv`, `views/menus.xml`, `__manifest__.py`, `tests/__init__.py`

**Interfaces:**
- Produces: `uam.access.simulation._rows() -> list[dict]` with keys `model` (str), `name` (str), and for each of `read, create, write, unlink`: `{'ok': bool, 'groups': list[str]}`; field `report_html`.

- [ ] **Step 1: Write the failing test** — `tests/test_simulation.py` (add import):

```python
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSimulation(TransactionCase):

    def test_matches_has_access(self):
        user = new_test_user(self.env, login='uam_sim', groups='base.group_user')
        wiz = self.env['uam.access.simulation'].create({
            'user_id': user.id, 'model_id': self.env['ir.model']._get('res.partner').id})
        row = wiz._rows()[0]
        partner_as_user = self.env['res.partner'].with_user(user)
        for op in ('read', 'create', 'write', 'unlink'):
            self.assertEqual(row[op]['ok'], partner_as_user.has_access(op), op)
        self.assertTrue(row['read']['groups'])
        self.assertIn('res.partner', wiz.report_html)

    def test_module_scope(self):
        wiz = self.env['uam.access.simulation'].create({
            'user_id': self.env.user.id,
            'module_id': self.env['ir.module.module'].search([('name', '=', 'user_access_management')]).id})
        self.assertIn('uam.print.log', [r['model'] for r in wiz._rows()])
```

- [ ] **Step 2: Run test** — expected FAIL `KeyError: 'uam.access.simulation'`.

- [ ] **Step 3: Implement** — `models/access_simulation.py`:

```python
from markupsafe import Markup

from odoo import api, fields, models

OPS = {'read': 'r', 'create': 'c', 'write': 'u', 'unlink': 'd'}


class UamAccessSimulation(models.TransientModel):
    _name = 'uam.access.simulation'
    _description = 'Access Simulation'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    model_id = fields.Many2one('ir.model', string='Model')
    module_id = fields.Many2one('ir.module.module', string='Module', domain=[('state', '=', 'installed')])
    report_html = fields.Html(compute='_compute_report_html', sanitize=False)

    def _models(self):
        if self.model_id:
            return self.model_id
        if self.module_id:
            ids = self.env['ir.model.data'].sudo().search(
                [('module', '=', self.module_id.name), ('model', '=', 'ir.model')]).mapped('res_id')
            return self.env['ir.model'].sudo().browse(ids).filtered(lambda m: not m.transient).sorted('model')
        return self.env['ir.model']

    def _rows(self):
        self.ensure_one()
        user = self.user_id.sudo()
        accesses = self.env['ir.access'].sudo().search([
            ('active', '=', True), ('group_id', 'in', user.all_group_ids.ids), ('model_id', 'in', self._models().ids)])
        rows = []
        for model in self._models():
            if model.model not in self.env:
                continue
            as_user = self.env(user=user.id)[model.model]
            row = {'model': model.model, 'name': model.name}
            for op, letter in OPS.items():
                granting = accesses.filtered(lambda a: a.model_id == model and letter in a.operation)
                row[op] = {'ok': as_user.has_access(op), 'groups': granting.group_id.mapped('full_name')}
            rows.append(row)
        return rows

    @api.depends('user_id', 'model_id', 'module_id')
    def _compute_report_html(self):
        for wiz in self:
            if not wiz.user_id or not (wiz.model_id or wiz.module_id):
                wiz.report_html = False
                continue
            head = Markup('<tr><th>Model</th>%s</tr>') % Markup('').join(
                Markup('<th>%s</th>') % op.capitalize() for op in ('create', 'read', 'write', 'unlink'))
            body = Markup('').join(
                Markup('<tr><td>%s<br/><small class="text-muted">%s</small></td>%s</tr>') % (
                    r['name'], r['model'], Markup('').join(
                        Markup('<td title="%s">%s</td>') % (', '.join(r[op]['groups']) or '-',
                                                            '✓' if r[op]['ok'] else '✗')
                        for op in ('create', 'read', 'write', 'unlink')))
                for r in wiz._rows())
            wiz.report_html = Markup('<table class="table table-sm table-bordered"><thead>%s</thead>'
                                     '<tbody>%s</tbody></table>') % (head, body)
```

Hovering a ✓/✗ cell shows the granting groups (`title`).

`security/ir.access.csv` — append `access_uam_access_simulation_admin,uam.access.simulation admin,uam.access.simulation,base.group_system,crud,`.

`views/access_simulation_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="access_simulation_view_form" model="ir.ui.view">
        <field name="name">uam.access.simulation.form</field>
        <field name="model">uam.access.simulation</field>
        <field name="arch" type="xml">
            <form>
                <group>
                    <group>
                        <field name="user_id" options="{'no_create': True}"/>
                    </group>
                    <group>
                        <field name="model_id" options="{'no_create': True}" invisible="module_id"/>
                        <field name="module_id" options="{'no_create': True}" invisible="model_id"/>
                    </group>
                </group>
                <field name="report_html" nolabel="1"/>
            </form>
        </field>
    </record>
    <record id="access_simulation_action" model="ir.actions.act_window">
        <field name="name">Access Simulation</field>
        <field name="res_model">uam.access.simulation</field>
        <field name="view_mode">form</field>
        <field name="target">current</field>
    </record>
</odoo>
```

`views/menus.xml` — `<menuitem id="menu_uam_simulation" name="Access Simulation" parent="menu_uam_privileges" action="access_simulation_action" sequence="70"/>`.
`models/__init__.py` — append `from . import access_simulation`. `__manifest__.py` — add view file before menus.

- [ ] **Step 4: Run tests** — expected exit 0.

- [ ] **Step 5: Manual check** — Privileges › Access Simulation, pick Mitchell Admin + model Contact → table with ✓/✗; switch to a module → many rows.

- [ ] **Step 6: Commit**

```bash
git add user_access_management/models/access_simulation.py user_access_management/models/__init__.py user_access_management/security/ir.access.csv user_access_management/views/access_simulation_views.xml user_access_management/views/menus.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): read-only access simulation per user and model/module"
```

---

### Task 6: Dashboard (home page)

**Files:**
- Create: `models/dashboard.py`, `static/src/dashboard/dashboard.js`, `static/src/dashboard/dashboard.xml`, `views/dashboard_views.xml`, `tests/test_dashboard.py`
- Modify: `models/__init__.py`, `models/res_users.py`, `data/uam_data.xml`, `views/menus.xml`, `__manifest__.py`, `tests/__init__.py`

**Interfaces:**
- Consumes: `res.users._uam_stale_limit()`, `uam_login_stale` (Task 1); `uam.print.log` (Task 2); `uam.access.lock` (Task 3); `uam_current_page`, `uam_last_seen`, `uam.model.usage` (Task 4); `user.temp.access` (existing).
- Produces: `uam.dashboard.get_data(date: str 'YYYY-MM-DD'|False) -> dict` with keys `tiles` (list of `{key, label, count, icon}`), `users` (list of `{id, name, status, page, last_seen, login_date, stale}`), `usage` (list of `{user_id, user, model, views, last_seen}`), `prints` (list of `{id, document, label, user, date, url}`), `date`; `uam.dashboard.open_tile(key: str) -> act_window dict`; `uam.dashboard.open_user_usage(user_id: int, date: str) -> act_window dict`; `res.users._uam_set_home_action()`.

- [ ] **Step 1: Write the failing test** — `tests/test_dashboard.py` (add import):

```python
from odoo import fields
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
        self.assertEqual(admin.action_id, self.env.ref('user_access_management.uam_dashboard_action'))
```

- [ ] **Step 2: Run test** — expected FAIL `KeyError: 'uam.dashboard'`.

- [ ] **Step 3: Implement backend** — `models/dashboard.py`:

```python
from datetime import timedelta

from odoo import api, fields, models


class UamDashboard(models.AbstractModel):
    _name = 'uam.dashboard'
    _description = 'User Access Dashboard'

    def _users(self):
        return self.env['res.users'].sudo().search([('share', '=', False)])

    def _tile_domains(self):
        now = fields.Datetime.now()
        users = self._users()
        today = fields.Datetime.to_string(fields.Datetime.start_of(now, 'day'))
        return {
            'online': ('res.users', [('id', 'in', users.filtered(lambda u: u.im_status == 'online').ids)]),
            'away': ('res.users', [('id', 'in', users.filtered(lambda u: u.im_status == 'away').ids)]),
            'stale': ('res.users', [('share', '=', False), ('uam_login_stale', '=', True)]),
            'locks': ('uam.access.lock', [('active', '=', True)]),
            'temp_expiring': ('user.temp.access', [('state', '=', 'active'), ('date_to', '<', now + timedelta(hours=24))]),
            'prints_today': ('uam.print.log', [('create_date', '>=', today)]),
        }

    @api.model
    def get_data(self, date=False):
        day = fields.Date.to_date(date) if date else fields.Date.context_today(self)
        labels = {'online': ('Online', 'fa-circle text-success'), 'away': ('Away', 'fa-circle text-warning'),
                  'stale': ('Stale logins', 'fa-exclamation-triangle text-danger'),
                  'locks': ('Active locks', 'fa-lock'), 'temp_expiring': ('Temp access expiring <24h', 'fa-clock-o'),
                  'prints_today': ('PDFs today', 'fa-print')}
        tiles = [{'key': k, 'label': labels[k][0], 'icon': labels[k][1],
                  'count': self.env[m].sudo().search_count(d)} for k, (m, d) in self._tile_domains().items()]
        order = {'online': 0, 'away': 1}
        users = sorted(self._users(), key=lambda u: (order.get(u.im_status, 2), u.name))
        usage = self.env['uam.model.usage'].sudo().search([('date', '=', day)], order='view_count desc', limit=50)
        prints = self.env['uam.print.log'].sudo().search([], limit=10)
        dt = fields.Datetime.to_string
        return {
            'date': fields.Date.to_string(day),
            'tiles': tiles,
            'users': [{'id': u.id, 'name': u.name, 'status': u.im_status, 'page': u.uam_current_page or '',
                       'last_seen': dt(u.uam_last_seen) if u.uam_last_seen else False,
                       'login_date': dt(u.login_date) if u.login_date else False,
                       'stale': u.uam_login_stale} for u in users],
            'usage': [{'user_id': r.user_id.id, 'user': r.user_id.name, 'model': r.model,
                       'model_name': r.model_name, 'views': r.view_count, 'last_seen': dt(r.last_seen)} for r in usage],
            'prints': [{'id': p.id, 'document': p.record_name or p.res_ids, 'label': p.label,
                        'user': p.user_id.name, 'date': dt(p.create_date),
                        'url': f'/web/content/{p.attachment_id.id}?download=true'} for p in prints],
        }

    @api.model
    def open_tile(self, key):
        model, domain = self._tile_domains()[key]
        return {'type': 'ir.actions.act_window', 'name': key.replace('_', ' ').title(), 'res_model': model,
                'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    @api.model
    def open_user_usage(self, user_id, date):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Model Usage'), 'res_model': 'uam.model.usage',
                'views': [(False, 'list')], 'domain': [('user_id', '=', user_id), ('date', '=', date)]}
```

`models/res_users.py` — add:

```python
    @api.model
    def _uam_set_home_action(self):
        action = self.env.ref('user_access_management.uam_dashboard_action')
        admins = self.sudo().search([('group_ids', 'in', self.env.ref('base.group_system').ids), ('action_id', '=', False)])
        admins.write({'action_id': action.id})
```

`views/dashboard_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="uam_dashboard_action" model="ir.actions.client">
        <field name="name">User Access Dashboard</field>
        <field name="tag">uam_dashboard</field>
    </record>
</odoo>
```

`data/uam_data.xml` — append (runs on every install/upgrade, only fills empty home actions):

```xml
    <function model="res.users" name="_uam_set_home_action"/>
```

`views/menus.xml` — set root `action="uam_dashboard_action"` on `menu_uam_root`, and add `<menuitem id="menu_uam_dashboard" name="Dashboard" parent="menu_uam_root" action="uam_dashboard_action" sequence="1"/>`.
`__manifest__.py` — add `'views/dashboard_views.xml'` **before** `'views/menus.xml'` and keep `'data/uam_data.xml'` after it. `models/__init__.py` — append `from . import dashboard`.

- [ ] **Step 4: Run tests** — expected exit 0.

- [ ] **Step 5: Implement frontend** — `static/src/dashboard/dashboard.js`:

```javascript
import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 30 * 1000;

export class UamDashboard extends Component {
    static template = "user_access_management.Dashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, date: "" });
        onWillStart(() => this.load());
        const timer = setInterval(() => this.load(), REFRESH_MS);
        onWillUnmount(() => clearInterval(timer));
    }

    async load() {
        this.state.data = await this.orm.call("uam.dashboard", "get_data", [this.state.date || false]);
        this.state.date = this.state.data.date;
    }

    onDate(ev) {
        this.state.date = ev.target.value;
        this.load();
    }

    async openTile(key) {
        this.action.doAction(await this.orm.call("uam.dashboard", "open_tile", [key]));
    }

    async openUsage(userId) {
        this.action.doAction(await this.orm.call("uam.dashboard", "open_user_usage", [userId, this.state.date]));
    }

    openUser(userId) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "res.users", res_id: userId,
                               views: [[false, "form"]] });
    }
}

registry.category("actions").add("uam_dashboard", UamDashboard);
```

`static/src/dashboard/dashboard.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="user_access_management.Dashboard">
        <div class="o_action p-3 overflow-auto h-100 bg-view">
            <t t-set="d" t-value="this.state.data"/>
            <div class="d-flex align-items-center mb-3">
                <h2 class="me-auto mb-0">User Access Dashboard</h2>
                <input type="date" class="form-control w-auto" t-att-value="this.state.date" t-on-change="this.onDate"/>
            </div>
            <div class="row g-2 mb-3">
                <div t-foreach="d.tiles" t-as="tile" t-key="tile.key" class="col-6 col-md-4 col-xl-2">
                    <div class="card h-100 cursor-pointer" t-on-click="() => this.openTile(tile.key)">
                        <div class="card-body">
                            <div class="fs-2 fw-bold" t-esc="tile.count"/>
                            <div class="text-muted"><i t-attf-class="fa {{ tile.icon }} me-1"/><t t-esc="tile.label"/></div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="card mb-3">
                <div class="card-header fw-bold">Users right now</div>
                <table class="table table-sm table-hover mb-0">
                    <thead><tr><th>User</th><th>Page open</th><th>Last seen</th><th>Last login</th></tr></thead>
                    <tbody>
                        <tr t-foreach="d.users" t-as="u" t-key="u.id">
                            <td>
                                <span t-attf-class="d-inline-block rounded-circle me-2 bg-{{ u.status === 'online' ? 'success' : u.status === 'away' ? 'warning' : 'secondary' }}" style="width: 10px; height: 10px;"/>
                                <a href="#" t-on-click.prevent="() => this.openUser(u.id)" t-esc="u.name"/>
                                <span t-if="u.stale" class="badge text-bg-danger ms-2">Stale</span>
                            </td>
                            <td t-esc="u.page"/>
                            <td t-esc="u.last_seen or '-'"/>
                            <td t-esc="u.login_date or 'never'"/>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="row g-3">
                <div class="col-lg-7">
                    <div class="card">
                        <div class="card-header fw-bold">Models used on <t t-esc="d.date"/></div>
                        <table class="table table-sm table-hover mb-0">
                            <thead><tr><th>User</th><th>Model</th><th class="text-end">Views</th><th>Last</th></tr></thead>
                            <tbody>
                                <tr t-foreach="d.usage" t-as="r" t-key="r_index" class="cursor-pointer" t-on-click="() => this.openUsage(r.user_id)">
                                    <td t-esc="r.user"/><td t-esc="r.model_name"/>
                                    <td class="text-end" t-esc="r.views"/><td t-esc="r.last_seen"/>
                                </tr>
                                <tr t-if="!d.usage.length"><td colspan="4" class="text-muted">No activity on this day.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="col-lg-5">
                    <div class="card">
                        <div class="card-header fw-bold">Recent prints</div>
                        <table class="table table-sm mb-0">
                            <tbody>
                                <tr t-foreach="d.prints" t-as="p" t-key="p.id">
                                    <td t-esc="p.document"/>
                                    <td><span t-attf-class="badge text-bg-{{ p.label === 'Original' ? 'success' : 'warning' }}" t-esc="p.label"/></td>
                                    <td t-esc="p.user"/>
                                    <td><a t-att-href="p.url" title="Download"><i class="fa fa-download"/></a></td>
                                </tr>
                                <tr t-if="!d.prints.length"><td class="text-muted">No prints yet.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </t>
</templates>
```

Note: `onWillStart` awaits the first load, so `d` is set before first render.

- [ ] **Step 6: Run tests** — expected exit 0.

- [ ] **Step 7: Playwright check on :8070** — log in as admin → lands on the dashboard (home action). Verify: 6 tiles with numbers; clicking "Online" opens a user list; "Users right now" shows your own row with the page you last opened; changing the date reloads the usage table; ⬇ in Recent prints downloads a PDF; no console errors. Take one screenshot for the user.

- [ ] **Step 8: Commit**

```bash
git add user_access_management/models/dashboard.py user_access_management/models/res_users.py user_access_management/models/__init__.py user_access_management/static/src/dashboard user_access_management/views/dashboard_views.xml user_access_management/views/menus.xml user_access_management/data/uam_data.xml user_access_management/__manifest__.py user_access_management/tests
git commit -m "feat(uam): admin dashboard as home page"
```

---

## Out of scope (from spec)

- Granting/removing rights from Simulation.
- Locking `type="action"` buttons.
- Watermarking copies.
