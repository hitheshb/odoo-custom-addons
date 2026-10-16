from markupsafe import Markup, escape

from odoo import api, fields, models

WORDS = {'read': 'view', 'create': 'add', 'write': 'change', 'unlink': 'delete'}


class AdminAccessSimulation(models.TransientModel):
    _name = 'admin.access.simulation'
    _description = 'User Access Simulation'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    report_html = fields.Html(compute='_compute_report_html', sanitize=False)

    @api.depends('user_id')
    def _compute_report_html(self):
        for wiz in self:
            wiz.report_html = wiz._build(wiz.user_id.sudo()) if wiz.user_id else False

    def _build(self, user):
        env_user = self.env(user=user.id)
        parts = [self._intro(user), self._menus(user), self._data(user, env_user)]
        return Markup('').join(parts)

    def _intro(self, user):
        groups = user.group_ids.sorted('full_name').mapped('full_name')
        is_admin = user.has_group('base.group_system')
        last = user.login_date and fields.Datetime.to_string(user.login_date) or 'never'
        out = [Markup('<h3>%s</h3>') % user.name]
        out.append(Markup('<p>Login <b>%s</b>. Account type: <b>%s</b>. Last login: <b>%s</b>.</p>') % (
            user.login, 'portal/external' if user.share else 'internal employee', last))
        if is_admin:
            out.append(Markup('<p><b>Full administrator:</b> can change any setting and see all data.</p>'))
        out.append(Markup('<p>Roles given to this person:</p><ul>%s</ul>') % Markup('').join(
            Markup('<li>%s</li>') % g for g in groups))
        return Markup('').join(out)

    def _menus(self, user):
        Menu = self.env['ir.ui.menu']
        visible = Menu.with_user(user.id)._visible_menu_ids()
        roots = Menu.sudo().browse(list(visible)).filtered(lambda m: not m.parent_id).sorted('sequence')
        return Markup('<h4>Apps this person can open</h4><p>%s</p>') % (
            ', '.join(roots.mapped('name')) or 'None')

    def _data(self, user, env_user):
        accesses = self.env['ir.access'].sudo().search([
            ('active', '=', True), '|', ('group_id', '=', False), ('group_id', 'in', user.all_group_ids.ids)])
        limited = {a.model_id.id for a in accesses if a.domain}
        by_ability = {}
        for model in accesses.model_id.sorted('name'):
            if model.model not in env_user.registry or model.transient:
                continue
            rec = env_user[model.model]
            ops = tuple(WORDS[op] for op in WORDS if rec.has_access(op))
            if ops:
                label = ', '.join(ops)
                by_ability.setdefault(label, []).append(model.name + (' *' if model.id in limited else ''))
        out = [Markup('<h4>What this person can do with data</h4>')]
        for label, names in sorted(by_ability.items(), key=lambda kv: -len(kv[0])):
            out.append(Markup('<p>Can <b>%s</b>: %s</p>') % (label, escape(', '.join(names))))
        if not by_ability:
            out.append(Markup('<p>No data access.</p>'))
        out.append(Markup('<p><i>* only for some records (restricted by a rule).</i></p>'))
        return Markup('').join(out)
