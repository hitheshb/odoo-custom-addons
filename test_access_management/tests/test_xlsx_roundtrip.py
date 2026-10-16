import base64

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..utils.xlsx_io import HEADERS, build_xlsx


@tagged('post_install', '-at_install')
class TestXlsxRoundtrip(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = cls.env.ref('base.model_res_partner')
        cls.group = cls.env.ref('base.group_partner_manager')
        cls.profile = cls.env['test.access.profile'].create({
            'name': 'Round Trip',
            'line_ids': [
                Command.create({
                    'name': 'Partners', 'model_id': cls.model.id, 'group_id': cls.group.id,
                    'for_create': True, 'for_write': True,
                }),
                Command.create({
                    'name': 'Own partners', 'model_id': cls.model.id,
                    'domain': "[('create_uid', '=', 1)]",
                }),
            ],
        })

    def _upload(self, content, profile):
        wizard = self.env['test.access.profile.upload'].create({
            'profile_id': profile.id,
            'file': base64.b64encode(content).decode(),
        })
        wizard.action_upload()
        return wizard

    def _snapshot(self, profile):
        return sorted(profile.line_ids._to_xlsx_rows())

    def test_roundtrip_changes_nothing(self):
        before = self._snapshot(self.profile)
        write_dates = self.profile.line_ids.mapped('write_date')
        wizard = self._upload(build_xlsx(self.profile.line_ids._to_xlsx_rows()), self.profile)
        self.assertFalse(wizard.error_report)
        self.assertEqual(self._snapshot(self.profile), before)
        self.assertEqual(self.profile.line_ids.mapped('write_date'), write_dates)

    def test_update_and_create(self):
        rows = self.profile.line_ids._to_xlsx_rows()
        rows[0][5] = False
        rows.append(['New line', 'res.partner', 'base.group_no_one', True, True, False, False, '', 'permission'])
        wizard = self._upload(build_xlsx(rows), self.profile)
        self.assertFalse(wizard.error_report)
        self.assertEqual(len(self.profile.line_ids), 3)

    def test_errors_collected_and_nothing_saved(self):
        rows = [
            ['Bad', 'no.such.model', 'base.nope', 'maybe', True, False, False, '[(', 'weird'],
            ['Dup', 'res.partner', '', True, True, True, True, '', 'restriction'],
            ['Dup', 'res.partner', '', True, True, True, True, '', 'restriction'],
        ]
        wizard = self._upload(build_xlsx(rows), self.profile)
        report = wizard.error_report
        for expected in ('Row 2, column Model', 'Row 2, column Group', 'Row 2, column Create',
                         'Row 2, column Kind', 'Row 4, columns Name/Model/Group'):
            self.assertIn(expected, report)
        self.assertEqual(len(self.profile.line_ids), 2)

    def test_header_problems(self):
        from openpyxl import Workbook
        import io
        workbook = Workbook()
        workbook.active.append(HEADERS[:-1] + ['Surprise'])
        buffer = io.BytesIO()
        workbook.save(buffer)
        wizard = self._upload(buffer.getvalue(), self.profile)
        self.assertIn('missing column(s): Kind', wizard.error_report)
        self.assertIn('unexpected column(s): Surprise', wizard.error_report)

    def test_user_upload_new_profile(self):
        user = self.env['res.users'].create({'name': 'Up User', 'login': 'up_user'})
        wizard = self.env['test.access.profile.upload'].create({
            'user_id': user.id,
            'target': 'new',
            'new_profile_name': 'Fresh',
            'file': base64.b64encode(build_xlsx(self.profile.line_ids._to_xlsx_rows())).decode(),
        })
        wizard.action_upload()
        self.assertEqual(user.test_profile_ids.name, 'Fresh')
        self.assertIn(self.group, user.group_ids)
