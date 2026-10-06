from collections import defaultdict

from odoo import Command, fields, models
from odoo.exceptions import AccessError, UserError

from ..utils.xlsx_io import read_xlsx


class TestAccessImport(models.TransientModel):
    _name = 'test.access.import'
    _description = 'Import groups from an access rights export'

    user_id = fields.Many2one('res.users', string='User', required=True)
    file = fields.Binary(string='XLSX File')
    filename = fields.Char()
    error_report = fields.Text(readonly=True)

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Import Groups'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only administrators can import groups.'))
        if not self.file:
            raise UserError(self.env._('Please choose an xlsx file first.'))
        errors, group_ids = self._parse()
        if errors:
            self.error_report = '\n'.join(errors)
            return self._reopen()
        missing = self.env['res.groups'].browse(group_ids) - self.user_id.all_group_ids
        self.user_id.write({'group_ids': [Command.link(g.id) for g in missing]})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Import finished'),
                'message': self.env._(
                    '%(added)s group(s) added to %(user)s: %(names)s',
                    added=len(missing), user=self.user_id.name,
                    names=', '.join(missing.mapped('full_name')) or '-'),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _parse(self):
        try:
            header, body = read_xlsx(self.file.content)
        except Exception as error:
            return [self.env._('The file is not a readable xlsx file: %s', error)], []
        if header != ['Group']:
            return [self.env._('Header row must be exactly one column named Group (use Export Groups).')], []

        groups_by_name = defaultdict(list)
        for group in self.env['res.groups'].search([]):
            groups_by_name[group.full_name].append(group.id)

        errors, found = [], {}
        for row, cells in body:
            label = str(cells[0] or '').strip() if cells else ''
            if not label or label in found:
                continue
            ids = groups_by_name.get(label, [])
            if len(ids) == 1:
                found[label] = ids[0]
            else:
                reason = 'ambiguous' if ids else 'unknown'
                errors.append(self.env._(
                    'Row %(row)s, column Group: %(reason)s value "%(value)s".',
                    row=row, reason=reason, value=label))
        return errors, list(found.values())
