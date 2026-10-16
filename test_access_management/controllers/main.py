from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request

from ..utils.xlsx_io import build_xlsx


class AccessExportController(http.Controller):

    @http.route(
        '/test_access_management/export/<string:kind>/<int:record_id>',
        type='http',
        auth='user',
    )
    def export_xlsx(self, kind, record_id):
        if not request.env.user.has_group('base.group_system'):
            raise Forbidden()
        if kind == 'groups':
            user = request.env['res.users'].browse(record_id).exists()
            if not user:
                raise NotFound()
            rows = [[name] for name in sorted(user.group_ids.mapped('full_name'))]
            return self._xlsx_response(build_xlsx(rows, ['Group']), f"groups_user_{record_id}.xlsx")
        if kind == 'profile':
            record = request.env['test.access.profile'].with_context(active_test=False).browse(record_id).exists()
            lines = record.line_ids
        elif kind == 'user':
            record = request.env['res.users'].browse(record_id).exists()
            lines = record.test_profile_ids.filtered('active').line_ids
        else:
            raise NotFound()
        if not record:
            raise NotFound()
        return self._xlsx_response(build_xlsx(lines._to_xlsx_rows()), f"access_{kind}_{record_id}.xlsx")

    @staticmethod
    def _xlsx_response(content, filename):
        return request.make_response(content, headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', f'attachment; filename="{filename}"'),
        ])
