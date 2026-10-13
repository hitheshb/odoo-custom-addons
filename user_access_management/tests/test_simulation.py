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

    def test_restriction_and_partial(self):
        user = new_test_user(self.env, login='uam_sim_r', groups='base.group_user')
        model = self.env['ir.model']._get('res.partner')
        acc = self.env['ir.access'].create({
            'name': 'uam sim restriction', 'model_id': model.id, 'operation': 'r',
            'domain': "[('id', '=', 0)]"})
        wiz = self.env['uam.access.simulation'].create({'user_id': user.id, 'model_id': model.id})
        cell = wiz._rows()[0]['read']
        self.assertIn(acc.name, cell['restrictions'])
        self.assertTrue(cell['partial'])
        self.assertEqual(cell['ok'], self.env['res.partner'].with_user(user).has_access('read'))
        self.assertIn('uam sim restriction', wiz.report_html)
        self.assertIn('only some records', wiz.report_html)

    def test_denied_cell(self):
        user = new_test_user(self.env, login='uam_sim_d', groups='base.group_user')
        wiz = self.env['uam.access.simulation'].create({
            'user_id': user.id, 'model_id': self.env['ir.model']._get('ir.model').id})
        row = wiz._rows()[0]
        self.assertFalse(row['write']['ok'])
        self.assertIn('✗', wiz.report_html)

    def test_group_name_escaped(self):
        group = self.env['res.groups'].create({'name': '<b>x</b>'})
        model = self.env['ir.model']._get('res.partner')
        self.env['ir.access'].create({
            'name': 'uam sim esc', 'model_id': model.id, 'group_id': group.id, 'operation': 'r'})
        user = new_test_user(self.env, login='uam_sim_e', groups='base.group_user')
        user.group_ids = [(4, group.id)]
        wiz = self.env['uam.access.simulation'].create({'user_id': user.id, 'model_id': model.id})
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', wiz.report_html)
        self.assertNotIn('<b>x</b>', wiz.report_html)

    def test_multi_company_context(self):
        main = self.env.company
        c2 = self.env['res.company'].create({'name': 'UAM Sim C2'})
        self.env.user.company_ids = [(4, c2.id)]
        user = new_test_user(self.env, login='uam_sim_mc', groups='base.group_user')
        user.write({'company_ids': [(6, 0, [main.id])], 'company_id': main.id})
        wiz = self.env['uam.access.simulation'].with_context(
            allowed_company_ids=[main.id, c2.id]).create({
                'user_id': user.id, 'model_id': self.env['ir.model']._get('res.partner').id})
        self.assertTrue(wiz._rows())

    def test_display_name(self):
        wiz = self.env['uam.access.simulation'].create({'user_id': self.env.user.id})
        self.assertEqual(wiz.display_name, f'Simulation: {self.env.user.name}')
