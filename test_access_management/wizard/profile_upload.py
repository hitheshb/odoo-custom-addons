from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..utils.xlsx_io import HEADERS, read_xlsx

TRUE_VALUES = {'true', '1', 'yes'}
FALSE_VALUES = {'false', '0', 'no'}
KINDS = ('permission', 'restriction')


class TestAccessProfileUpload(models.TransientModel):
    _name = 'test.access.profile.upload'
    _description = 'Upload access lines from xlsx'

    file = fields.Binary(string='XLSX File')
    filename = fields.Char()
    user_id = fields.Many2one('res.users', string='User')
    profile_id = fields.Many2one('test.access.profile', string='Profile')
    target = fields.Selection(
        [('existing', 'Existing profile of this user'), ('new', 'New profile for this user')],
        default='existing',
    )
    new_profile_name = fields.Char(string='New Profile Name')
    error_report = fields.Text(readonly=True)

    @api.model
    def _open_action(self, **defaults):
        return self.create(defaults)._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Upload Access Lines'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_upload(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only administrators can upload access lines.'))
        if not self.file:
            raise UserError(self.env._('Please choose an xlsx file first.'))
        profile = self._resolve_target()
        errors, rows = self._parse()
        if errors:
            self.error_report = '\n'.join(errors)
            return self._reopen()
        profile = profile or self._create_target_profile()
        self._apply(profile, rows)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'test.access.profile',
            'res_id': profile.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _resolve_target(self):
        if not self.user_id:
            if not self.profile_id:
                raise UserError(self.env._('No target profile.'))
            return self.profile_id
        if self.target == 'new':
            if not (self.new_profile_name or '').strip():
                raise UserError(self.env._('Enter a name for the new profile.'))
            return self.env['test.access.profile']
        if not self.profile_id:
            raise UserError(self.env._("Choose which of the user's profiles receives the rows."))
        if self.profile_id not in self.user_id.test_profile_ids:
            raise UserError(self.env._('That profile does not belong to this user.'))
        return self.profile_id

    def _create_target_profile(self):
        return self.env['test.access.profile'].create({
            'name': self.new_profile_name.strip(),
            'user_ids': [(4, self.user_id.id)],
        })

    def _parse(self):
        try:
            header, body = read_xlsx(self.file.content)
        except Exception as error:
            return [self.env._('The file is not a readable xlsx file: %s', error)], []

        errors = []
        missing = [name for name in HEADERS if name not in header]
        extra = [name for name in header if name and name not in HEADERS]
        if missing:
            errors.append(self.env._('Header row: missing column(s): %s', ', '.join(missing)))
        if extra:
            errors.append(self.env._('Header row: unexpected column(s): %s', ', '.join(extra)))
        if len(set(header)) != len(header):
            errors.append(self.env._('Header row: a column name appears more than once.'))
        if errors:
            return errors, []

        index = {name: header.index(name) for name in HEADERS}
        models_by_name = {m.model: m.id for m in self.env['ir.model'].sudo().search([])}
        rows = []
        seen = {}
        for row_number, cells in body:
            values = {name: (cells[pos] if pos < len(cells) else None) for name, pos in index.items()}
            if all(self._is_blank(v) for v in values.values()):
                continue
            row_errors, vals = self._validate_row(row_number, values, models_by_name)
            errors.extend(row_errors)
            if vals:
                key = (vals['name'], vals['model_id'], vals['group_id'])
                if key in seen:
                    errors.append(self.env._(
                        'Row %(row)s, columns Name/Model/Group: duplicate of row %(first)s.',
                        row=row_number, first=seen[key],
                    ))
                else:
                    seen[key] = row_number
                    rows.append((row_number, vals))
        return errors, rows

    @staticmethod
    def _is_blank(value):
        return value is None or (isinstance(value, str) and not value.strip())

    def _text(self, value):
        return '' if self._is_blank(value) else str(value).strip()

    def _validate_row(self, row, values, models_by_name):
        errors = []
        vals = {}

        name = self._text(values['Name'])
        if not name:
            errors.append(self.env._('Row %s, column Name: value is required.', row))
        vals['name'] = name

        model_name = self._text(values['Model'])
        model_id = models_by_name.get(model_name)
        if not model_name:
            errors.append(self.env._('Row %s, column Model: value is required.', row))
        elif not model_id:
            errors.append(self.env._(
                'Row %(row)s, column Model: unknown model "%(value)s".', row=row, value=model_name))
        vals['model_id'] = model_id

        group_id = False
        group_xmlid = self._text(values['Group'])
        group_ok = True
        if group_xmlid:
            group = self.env.ref(group_xmlid, raise_if_not_found=False) if '.' in group_xmlid else None
            if not group or group._name != 'res.groups':
                group_ok = False
                errors.append(self.env._(
                    'Row %(row)s, column Group: unknown group external ID "%(value)s".',
                    row=row, value=group_xmlid))
            else:
                group_id = group.id
        vals['group_id'] = group_id

        for column, field in (
            ('Create', 'for_create'), ('Read', 'for_read'),
            ('Update', 'for_write'), ('Delete', 'for_unlink'),
        ):
            flag = self._to_bool(values[column])
            if flag is None:
                errors.append(self.env._(
                    'Row %(row)s, column %(column)s: "%(value)s" is not a boolean (use TRUE/FALSE, 1/0, yes/no).',
                    row=row, column=column, value=self._text(values[column])))
            vals[field] = flag

        domain = self._text(values['Domain'])
        if domain and model_id:
            problem = self.env['test.access.profile.line']._domain_error(model_name, domain)
            if problem:
                errors.append(self.env._('Row %(row)s, column Domain: %(problem)s', row=row, problem=problem))
        vals['domain'] = domain or False

        kind = self._text(values['Kind']).lower()
        if kind not in KINDS:
            errors.append(self.env._(
                'Row %(row)s, column Kind: "%(value)s" is invalid (allowed: %(allowed)s).',
                row=row, value=kind, allowed=', '.join(KINDS)))
        elif group_ok:
            expected = 'permission' if group_id else 'restriction'
            if kind != expected:
                errors.append(self.env._(
                    'Row %(row)s, column Kind: must be "%(expected)s" for this row.',
                    row=row, expected=expected))

        return errors, (None if errors else vals)

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in TRUE_VALUES:
                return True
            if text in FALSE_VALUES:
                return False
        return None

    def _apply(self, profile, rows):
        existing = {
            (line.name, line.model_id.id, line.group_id.id): line
            for line in profile.line_ids
        }
        commands = []
        for _row_number, vals in rows:
            key = (vals['name'], vals['model_id'], vals['group_id'])
            line = existing.get(key)
            if line:
                changed = {
                    field: value for field, value in vals.items()
                    if field not in ('name', 'model_id', 'group_id') and line[field] != value
                }
                if changed:
                    commands.append((1, line.id, changed))
            else:
                commands.append((0, 0, vals))
        if commands:
            profile.write({'line_ids': commands})
