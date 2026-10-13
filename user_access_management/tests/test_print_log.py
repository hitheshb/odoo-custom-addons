from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import ConcurrencyError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


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

    def test_huge_batch_uses_hash_key(self):
        log = self.Log._record(self.report, list(range(1, 3001)), b'%PDF')
        self.assertEqual(len(log.res_key), 40)
        self.assertEqual(log.copy_no, 0)

    def test_unique_constraint_on_res_key(self):
        log = self.Log._record(self.report, [11], b'%PDF')
        vals = {'report_id': log.report_id.id, 'res_ids': '11', 'res_key': log.res_key, 'copy_no': 0}
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.Log.create(vals)

    def test_race_raises_concurrency_error(self):
        self.Log._record(self.report, [13], b'%PDF')
        with patch.object(type(self.Log), 'search_count', return_value=0), \
                mute_logger('odoo.sql_db'), self.assertRaises(ConcurrencyError):
            self.Log._record(self.report, [13], b'%PDF')
