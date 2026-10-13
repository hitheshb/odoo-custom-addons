from datetime import timedelta

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_datetime

FIXED_METHODS = [('create', 'Create'), ('write', 'Edit'), ('unlink', 'Delete'), ('print', 'Print')]
PROTECTED_MODELS = {'uam.access.lock', 'uam.lock.method'}
ADMIN_MODELS = {'res.users', 'res.groups', 'ir.access'}


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

    user_id = fields.Many2one('res.users', ondelete='cascade', index=True)
    group_id = fields.Many2one('res.groups', string='Group', ondelete='cascade', index=True,
                               help="Lock everyone in this group, including people who join later.")
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', index=True)
    method_ids = fields.Many2many('uam.lock.method', string='Methods', required=True,
                                  domain="[('model_id', '=', model_id)]")
    date_until = fields.Datetime('Locked Until')
    forever = fields.Boolean()
    active = fields.Boolean(default=True)
    note = fields.Char()
    lock_state = fields.Selection([('active', 'Active'), ('forever', 'Forever'), ('expired', 'Expired')],
                                  compute='_compute_lock_state')

    @api.depends('active', 'forever', 'date_until')
    def _compute_lock_state(self):
        now = fields.Datetime.now()
        for lock in self:
            if not lock.active or (not lock.forever and lock.date_until and lock.date_until <= now):
                lock.lock_state = 'expired'
            else:
                lock.lock_state = 'forever' if lock.forever else 'active'

    @api.constrains('user_id', 'group_id', 'model_id')
    def _check_target(self):
        admins = self.env.ref('base.group_system').all_user_ids
        for lock in self:
            if bool(lock.user_id) == bool(lock.group_id):
                raise ValidationError(self.env._('Choose either a user or a group, not both.'))
            if lock.model_id.model in PROTECTED_MODELS:
                raise ValidationError(self.env._('The Access Lock screen itself cannot be locked.'))
            targets = lock.user_id | lock.group_id.all_user_ids
            if lock.model_id.model in ADMIN_MODELS and targets & admins:
                raise ValidationError(self.env._(
                    'This lock would block an administrator from managing users and rights.'))

    def action_unlock(self):
        self.active = False

    def _extend(self, delta):
        now = fields.Datetime.now()
        for lock in self.filtered(lambda l: not l.forever):
            lock.date_until = max(lock.date_until or now, now) + delta
            lock.active = True

    def action_extend_day(self):
        self._extend(timedelta(days=1))

    def action_extend_week(self):
        self._extend(timedelta(weeks=1))

    @api.constrains('forever', 'date_until')
    def _check_until(self):
        for lock in self:
            if not lock.forever and not lock.date_until:
                raise ValidationError(self.env._("Set 'Locked Until' or tick 'Forever'."))

    @api.depends('user_id', 'group_id', 'model_id')
    def _compute_display_name(self):
        for lock in self:
            target = lock.user_id.name or lock.group_id.full_name
            lock.display_name = (f'{target} – {lock.model_id.name}'
                                 if target and lock.model_id else self.env._('New Lock'))

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if not vals.get('forever') and vals.get('date_until') and fields.Datetime.to_datetime(vals['date_until']) <= now:
                raise ValidationError(self.env._("'Locked Until' must be in the future."))
        return super().create(vals_list)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        self.method_ids = False
        if self.model_id:
            self.env['uam.lock.method'].sudo()._sync_for_model(self.model_id.model)

    @api.model
    def _method_key(self, method, args):
        """Map an RPC method to a lock key. Child records saved through a parent form's
        web_save are not checked against the child model."""
        if method in ('copy', 'name_create', 'load'):
            return 'create'
        if method == 'web_resequence':
            return 'write'
        if method in ('web_save', 'web_save_multi'):
            return 'write' if args and args[0] else 'create'
        if method == 'web_unlink':
            return 'unlink'
        return method

    @api.model
    def _check(self, model, method, args):
        key = self._method_key(method, args)
        lock = self.sudo().search([
            '|', ('user_id', '=', self.env.uid), ('group_id', 'in', self.env.user.sudo().all_group_ids.ids),
            ('model_id.model', '=', model), ('method_ids.name', '=', key),
            '|', ('forever', '=', True), ('date_until', '>', fields.Datetime.now()),
        ], limit=1)
        if lock:
            label = lock.method_ids.filtered(lambda m: m.name == key)[:1].label or key
            until = self.env._('forever') if lock.forever else format_datetime(self.env, lock.date_until)
            raise UserError(self.env._('Locked by administrator until %(until)s: %(label)s on %(model)s',
                                       until=until, label=label, model=lock.model_id.name))

    @api.model
    def _cron_archive_expired(self):
        self.search([('forever', '=', False), ('date_until', '<=', fields.Datetime.now())]).active = False
