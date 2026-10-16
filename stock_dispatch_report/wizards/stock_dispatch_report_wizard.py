from dateutil.relativedelta import relativedelta

from odoo import fields, models


class StockDispatchReportWizard(models.TransientModel):
    _name = 'stock.dispatch.report.wizard'
    _description = 'Dispatch Report Date Filter'

    date_from = fields.Date(
        string='From', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='To', required=True,
        default=lambda self: fields.Date.context_today(self))

    def _get_domain(self):
        self.ensure_one()
        date_from = fields.Datetime.to_datetime(self.date_from)
        date_to = fields.Datetime.to_datetime(self.date_to) + relativedelta(days=1)
        return [
            ('scheduled_date', '>=', date_from),
            ('scheduled_date', '<', date_to),
        ]

    def action_view_list(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock_dispatch_report.action_stock_dispatch_report')
        action['domain'] = self._get_domain()
        return action

    def action_download_xlsx(self):
        self.ensure_one()
        url = (
            '/stock_dispatch_report/xlsx'
            f'?date_from={self.date_from}&date_to={self.date_to}'
        )
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }
