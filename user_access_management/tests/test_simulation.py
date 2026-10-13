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
