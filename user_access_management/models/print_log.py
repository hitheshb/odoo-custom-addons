import hashlib

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError


class UamPrintLog(models.Model):
    _name = 'uam.print.log'
    _description = 'Print Log'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True, default=lambda self: self.env.uid)
    report_id = fields.Many2one('ir.actions.report', required=True, readonly=True, ondelete='cascade', index=True)
    model = fields.Char(readonly=True)
    res_ids = fields.Text('Record IDs', required=True, readonly=True)
    res_key = fields.Char(required=True, readonly=True, index=True)
    record_name = fields.Char('Document', readonly=True)
    copy_no = fields.Integer(readonly=True)
    label = fields.Char(compute='_compute_label')
    attachment_id = fields.Many2one('ir.attachment', readonly=True)

    _uniq_copy = models.Constraint('UNIQUE(report_id, res_key, copy_no)', 'This copy number already exists.')

    @api.depends('copy_no')
    def _compute_label(self):
        for log in self:
            log.label = f'Copy-{log.copy_no}' if log.copy_no else 'Original'

    @api.depends('record_name', 'res_ids', 'copy_no')
    def _compute_display_name(self):
        for log in self:
            log.display_name = f'{log.record_name or (log.res_ids or "")[:50]} ({log.label})'

    @api.model
    def _record(self, report, res_ids, content):
        ids = sorted(set(res_ids))
        key = ','.join(map(str, ids))
        names = ', '.join(self.env[report.model].browse(ids[:20]).exists().mapped('display_name'))
        if len(ids) > 20:
            names += f' +{len(ids) - 20} more'
        res_key = hashlib.sha1(key.encode()).hexdigest()
        try:
            with self.env.cr.savepoint():
                log = self.create({
                    'report_id': report.id, 'model': report.model, 'res_ids': key, 'res_key': res_key,
                    'record_name': names[:250],
                    'copy_no': self.search_count([('report_id', '=', report.id), ('res_key', '=', res_key)]),
                })
        except IntegrityError as e:
            # REPEATABLE READ: retrying here would see the same snapshot; let the request retry instead
            raise ConcurrencyError('Concurrent print of the same document') from e
        log.attachment_id = self.env['ir.attachment'].create({
            'name': f'{report.name} - {log.record_name or key} ({log.label}).pdf',
            'raw': content, 'mimetype': 'application/pdf',
            'res_model': self._name, 'res_id': log.id,
        })
        return log

    def action_download(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{self.attachment_id.id}?download=true',
                'target': 'self'}
