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

    def _rows(self):
        self.ensure_one()
        user = self.user_id.sudo()
        models_ = self._models()
        accesses = self.env['ir.access'].sudo().search([
            ('active', '=', True), ('model_id', 'in', models_.ids),
            '|', ('group_id', '=', False), ('group_id', 'in', user.all_group_ids.ids)])
        rows = []
        for model in models_:
            if model.model not in self.env:
                continue
            # fresh context: the admin's allowed_company_ids may be invalid for the simulated user
            as_user = self.env(user=user.id, context={'lang': self.env.lang})[model.model]
            row = {'model': model.model, 'name': model.name}
            for op, letter in OPS.items():
                covering = accesses.filtered(lambda a: a.model_id == model and letter in a.operation)
                granting = covering.filtered('group_id')
                restricting = covering - granting
                row[op] = {
                    'ok': as_user.has_access(op),
                    'groups': granting.group_id.mapped('full_name'),
                    'restrictions': restricting.mapped('name'),
                    'partial': any(a.domain and a.domain.strip() != '[]' for a in covering),
                }
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
                        Markup('<td title="%s">%s</td>') % (wiz._cell_title(r[op]), wiz._cell_glyph(r[op]))
                        for op in ('create', 'read', 'write', 'unlink')))
                for r in wiz._rows())
            wiz.report_html = Markup('<table class="table table-sm table-bordered"><thead>%s</thead>'
                                     '<tbody>%s</tbody></table>') % (head, body)
