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
