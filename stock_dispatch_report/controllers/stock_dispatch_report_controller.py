import io

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition

FIELDS = [
    ('reference', 'Reference'),
    ('product_id', 'Product'),
    ('default_code', 'Internal Reference'),
    ('product_uom_qty', 'Demand'),
    ('qty_done', 'Done'),
    ('quantity', 'Quantity'),
    ('uom_id', 'UoM'),
    ('picking_code', 'Type of Operation'),
    ('partner_id', 'Partner'),
    ('scheduled_date', 'Scheduled Date'),
    ('state', 'Status'),
]


class StockDispatchReportController(Controller):

    @route('/stock_dispatch_report/xlsx', type='http', auth='user', readonly=True)
    def download_xlsx(self, date_from, date_to):
        date_from_dt = fields.Datetime.to_datetime(date_from)
        date_to_dt = fields.Datetime.to_datetime(date_to) + relativedelta(days=1)
        domain = [
            ('scheduled_date', '>=', date_from_dt),
            ('scheduled_date', '<', date_to_dt),
        ]
        records = request.env['stock.dispatch.report'].search_read(
            domain, [f[0] for f in FIELDS])

        headers = [label for _, label in FIELDS]
        rows = []
        for record in records:
            row = []
            for fname, _ in FIELDS:
                value = record[fname]
                if isinstance(value, tuple):
                    value = value[1]
                row.append(value)
            rows.append(row)

        buffer = io.BytesIO()
        import xlsxwriter  # noqa: PLC0415
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        worksheet = workbook.add_worksheet()
        worksheet.write_row(0, 0, headers)
        column_widths = [len(header) for header in headers]
        for row_idx, row in enumerate(rows, start=1):
            worksheet.write_row(row_idx, 0, row)
            for col_idx, cell_value in enumerate(row):
                column_widths[col_idx] = max(column_widths[col_idx], len(str(cell_value)))
        for col_idx, width in enumerate(column_widths):
            worksheet.set_column(col_idx, col_idx, width)
        workbook.close()
        content = buffer.getvalue()
        buffer.close()

        response_headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            (
                'Content-Disposition',
                content_disposition(f'Dispatch Report - {date_from} to {date_to}.xlsx'),
            ),
        ]
        return request.make_response(content, response_headers)
