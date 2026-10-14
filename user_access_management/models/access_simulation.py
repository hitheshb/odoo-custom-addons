from markupsafe import Markup

from odoo import api, fields, models

OPS = {'read': 'r', 'create': 'c', 'write': 'u', 'unlink': 'd'}


class UamAccessSimulation(models.TransientModel):
    _name = 'uam.access.simulation'
    _description = 'Access Simulation'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    user2_id = fields.Many2one('res.users', string='Compare with')
    only_diff = fields.Boolean('Only differences')
    model_id = fields.Many2one('ir.model', string='Model')
    module_id = fields.Many2one('ir.module.module', string='Module', domain=[('state', '=', 'installed')])
    report_html = fields.Html(compute='_compute_report_html', sanitize=False)

    @api.depends('user_id')
    def _compute_display_name(self):
        for wiz in self:
            wiz.display_name = self.env._('Simulation: %s', wiz.user_id.name or '')

    def _models(self):
        if self.model_id:
            return self.model_id
        if self.module_id:
            ids = self.env['ir.model.data'].sudo().search(
                [('module', '=', self.module_id.name), ('model', '=', 'ir.model')]).mapped('res_id')
            return self.env['ir.model'].sudo().browse(ids).filtered(lambda m: not m.transient).sorted('model')
        return self.env['ir.model']

    def _cells(self, user, model, accesses):
        # fresh context: the admin's allowed_company_ids may be invalid for the simulated user
        as_user = self.env(user=user.id, context={'lang': self.env.lang})[model.model]
        cells = {}
        for op, letter in OPS.items():
            covering = accesses.filtered(lambda a: a.model_id == model and letter in a.operation)
            granting = covering.filtered(lambda a: a.group_id and a.group_id in user.all_group_ids)
            restricting = covering.filtered(lambda a: not a.group_id)
            cells[op] = {
                'ok': as_user.has_access(op),
                'groups': granting.group_id.mapped('full_name'),
                'restrictions': restricting.mapped('name'),
                'partial': any(a.domain and a.domain.strip() != '[]' for a in covering),
            }
        return cells

    def _rows(self):
        self.ensure_one()
        user = self.user_id.sudo()
        user2 = self.user2_id.sudo()
        models_ = self._models()
        accesses = self.env['ir.access'].sudo().search([
            ('active', '=', True), ('model_id', 'in', models_.ids),
            '|', ('group_id', '=', False), ('group_id', 'in', (user.all_group_ids | user2.all_group_ids).ids)])
        rows = []
        for model in models_:
            if model.model not in self.env:
                continue
            row = {'model': model.model, 'name': model.name, **self._cells(user, model, accesses)}
            if user2:
                row['other'] = self._cells(user2, model, accesses)
                row['diff'] = any(row[op]['ok'] != row['other'][op]['ok'] for op in OPS)
            rows.append(row)
        return rows

    @staticmethod
    def _cell_glyph(cell):
        return ('✓*' if cell['partial'] else '✓') if cell['ok'] else '✗'

    @staticmethod
    def _cell_title(cell):
        parts = [', '.join(cell['groups']) or '-']
        if cell['restrictions']:
            parts.append('restricted by: ' + ', '.join(cell['restrictions']))
        if cell['partial']:
            parts.append('only some records')
        return '; '.join(parts)

    @staticmethod
    def _cell_class(cell):
        return 'o_uam_cell--partial' if cell['ok'] and cell['partial'] else (
            'o_uam_cell--ok' if cell['ok'] else 'o_uam_cell--no')

    def _td(self, cell):
        return Markup('<td class="%s" title="%s">%s</td>') % (
            self._cell_class(cell), self._cell_title(cell), self._cell_glyph(cell))

    @api.depends('user_id', 'user2_id', 'only_diff', 'model_id', 'module_id')
    def _compute_report_html(self):
        ops = ('create', 'read', 'write', 'unlink')
        for wiz in self:
            if not wiz.user_id or not (wiz.model_id or wiz.module_id):
                wiz.report_html = False
                continue
            if wiz.user2_id:
                head = Markup('<tr><th rowspan="2">Model</th>%s</tr><tr>%s</tr>') % (
                    Markup('').join(Markup('<th colspan="2">%s</th>') % op.capitalize() for op in ops),
                    Markup('').join(
                        Markup('<th>%s</th><th>%s</th>') % (wiz.user_id.name, wiz.user2_id.name) for op in ops))
            else:
                head = Markup('<tr><th>Model</th>%s</tr>') % Markup('').join(
                    Markup('<th>%s</th>') % op.capitalize() for op in ops)
            body = Markup('')
            for r in wiz._rows():
                if wiz.user2_id and wiz.only_diff and not r['diff']:
                    continue
                cells = Markup('').join(
                    wiz._td(r[op]) + (wiz._td(r['other'][op]) if wiz.user2_id else Markup(''))
                    for op in ops)
                body += Markup('<tr class="%s"><td>%s<br/><small class="text-muted">%s</small></td>%s</tr>') % (
                    'o_uam_diff' if r.get('diff') else '', r['name'], r['model'], cells)
            wiz.report_html = Markup('<table class="table table-sm table-bordered"><thead>%s</thead>'
                                     '<tbody>%s</tbody></table>') % (head, body)
