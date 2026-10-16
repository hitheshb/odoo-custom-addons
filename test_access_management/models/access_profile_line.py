import ast

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class TestAccessProfileLine(models.Model):
    _name = 'test.access.profile.line'
    _description = 'Access Profile Line'
    _order = 'profile_id, model_id, group_id, id'

    profile_id = fields.Many2one(
        'test.access.profile',
        string='Profile',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(required=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    group_id = fields.Many2one('res.groups', string='Group', ondelete='cascade')
    for_create = fields.Boolean(string='Create')
    for_read = fields.Boolean(string='Read', default=True)
    for_write = fields.Boolean(string='Update')
    for_unlink = fields.Boolean(string='Delete')
    domain = fields.Char()
    kind = fields.Selection(
        [('permission', 'Permission'), ('restriction', 'Restriction')],
        compute='_compute_kind',
        store=True,
    )

    @api.depends('group_id')
    def _compute_kind(self):
        for line in self:
            line.kind = 'permission' if line.group_id else 'restriction'

    @api.constrains('profile_id', 'name', 'model_id', 'group_id')
    def _check_unique_key(self):
        for line in self:
            duplicates = self.search_count([
                ('id', '!=', line.id),
                ('profile_id', '=', line.profile_id.id),
                ('name', '=', line.name),
                ('model_id', '=', line.model_id.id),
                ('group_id', '=', line.group_id.id),
            ])
            if duplicates:
                raise ValidationError(self.env._(
                    'A line with the same Name, Model and Group already exists in this profile.'
                ))

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for line in self:
            error = self._domain_error(line.model_id.model, line.domain)
            if error:
                raise ValidationError(error)

    @api.model
    def _domain_error(self, model_name, domain_text):
        domain_text = (domain_text or '').strip()
        if not domain_text:
            return None
        try:
            domain = Domain(ast.literal_eval(domain_text))
        except (ValueError, SyntaxError, TypeError):
            return self.env._('Domain is not a valid domain expression: %s', domain_text)
        if model_name not in self.env:
            return self.env._('Model %s is not available.', model_name)
        try:
            domain.validate(self.env[model_name])
        except Exception as error:
            return self.env._('Domain does not fit model %(model)s: %(error)s', model=model_name, error=error)
        return None

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.profile_id.user_ids._test_sync_profile_groups()
        return lines

    def write(self, vals):
        users = self.profile_id.user_ids
        result = super().write(vals)
        (users | self.profile_id.user_ids)._test_sync_profile_groups()
        return result

    def unlink(self):
        users = self.profile_id.user_ids
        result = super().unlink()
        users._test_sync_profile_groups()
        return result

    def _to_xlsx_rows(self):
        external_ids = self.group_id.get_external_id()
        rows = []
        for line in self:
            group_xmlid = ''
            if line.group_id:
                group_xmlid = external_ids.get(line.group_id.id)
                if not group_xmlid:
                    raise UserError(self.env._(
                        'Group "%s" has no external ID, so it cannot be exported.',
                        line.group_id.display_name,
                    ))
            rows.append([
                line.name,
                line.model_id.model,
                group_xmlid,
                line.for_create,
                line.for_read,
                line.for_write,
                line.for_unlink,
                line.domain or '',
                line.kind,
            ])
        return rows
