import json
import logging

from odoo import http
from odoo.exceptions import ConcurrencyError
from odoo.http import request, route

from odoo.addons.rpc.controllers.json2 import WebJson2Controller
from odoo.addons.web.controllers.dataset import DataSet
from odoo.addons.web.controllers.report import ReportController

_logger = logging.getLogger(__name__)


def _parse_report_url(url, type_):
    """Return (report, ids) for a '/report/pdf/<name>/<ids>' download, else (None, [])."""
    if not type_.startswith('qweb-pdf') or '/report/pdf/' not in url:
        return None, []
    name = url.split('/report/pdf/')[1].split('?')[0]
    if '/' not in name:
        return None, []
    name, docids = name.split('/', 1)
    report = request.env['ir.actions.report']._get_report_from_name(name)
    return report, [int(i) for i in docids.split(',') if i.isdigit()]


class UamReportController(ReportController):

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        # every /report/<converter>/... GET (and report_download, which calls this) hits the print lock
        report = request.env['ir.actions.report']._get_report_from_name(reportname)
        if report:
            ids = [int(i) for i in docids.split(',') if i.isdigit()] if isinstance(docids, str) else docids or []
            request.env['uam.access.lock']._check(report.model, 'print', [ids])
        return super().report_routes(reportname, docids=docids, converter=converter, **data)

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        url, type_ = json.loads(data)[:2]
        report, ids = _parse_report_url(url, type_)
        response = super().report_download(data, context=context, token=token, readonly=readonly)
        if report and ids and response.status_code == 200 and response.mimetype == 'application/pdf':
            try:
                with request.env.cr.savepoint():
                    request.env['uam.print.log'].sudo()._record(report, ids, response.get_data())
            except ConcurrencyError:
                raise
            except Exception:
                _logger.exception('Could not log print of report %s', report.report_name)
        return response


class UamDataSet(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        request.env['uam.access.lock']._check(model, method, args)
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        request.env['uam.access.lock']._check(model, method, args)
        return super().call_button(model, method, args, kwargs, path=path)


class UamJson2(WebJson2Controller):

    @http.route()
    def web_json_2_rpc(self, __model__, __method__, ids=(), context=None, **kwargs):
        request.env['uam.access.lock']._check(__model__, __method__, [list(ids)])
        if context is None:
            return super().web_json_2_rpc(__model__, __method__, ids=ids, **kwargs)
        return super().web_json_2_rpc(__model__, __method__, ids=ids, context=context, **kwargs)
