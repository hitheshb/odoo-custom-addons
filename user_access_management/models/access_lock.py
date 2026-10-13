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
