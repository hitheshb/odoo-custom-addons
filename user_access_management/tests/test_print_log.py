from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrintLog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env['ir.actions.report'].search([('report_type', '=', 'qweb-pdf')], limit=1)
        cls.Log = cls.env['uam.print.log'].sudo()

    def test_original_then_copies(self):
        first = self.Log._record(self.report, [1], b'%PDF-a')
        second = self.Log._record(self.report, [1], b'%PDF-b')
        third = self.Log._record(self.report, [1], b'%PDF-c')
        self.assertEqual([first.label, second.label, third.label], ['Original', 'Copy-1', 'Copy-2'])
        self.assertEqual(second.attachment_id.raw.content, b'%PDF-b')

    def test_multi_record_order_independent(self):
        self.Log._record(self.report, [5, 3], b'%PDF')
        again = self.Log._record(self.report, [3, 5], b'%PDF')
        self.assertEqual(again.res_ids, '3,5')
        self.assertEqual(again.copy_no, 1)

    def test_download_action_points_to_attachment(self):
        log = self.Log._record(self.report, [7], b'%PDF')
        action = log.action_download()
        self.assertEqual(action['url'], f'/web/content/{log.attachment_id.id}?download=true')
