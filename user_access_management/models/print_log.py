from psycopg2 import IntegrityError

from odoo import api, fields, models


class UamPrintLog(models.Model):
    _name = 'uam.print.log'
    _description = 'Print Log'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True, default=lambda self: self.env.uid)
    report_id = fields.Many2one('ir.actions.report', required=True, readonly=True, ondelete='cascade', index=True)
    model = fields.Char(readonly=True)
    res_ids = fields.Char('Record IDs', required=True, readonly=True, index=True)
    record_name = fields.Char('Document', readonly=True)
    copy_no = fields.Integer(readonly=True)
    label = fields.Char(compute='_compute_label')
    attachment_id = fields.Many2one('ir.attachment', readonly=True)

    _uniq_copy = models.Constraint('UNIQUE(report_id, res_ids, copy_no)', 'This copy number already exists.')

    @api.depends('copy_no')
    def _compute_label(self):
        for log in self:
            log.label = f'Copy-{log.copy_no}' if log.copy_no else 'Original'

    @api.model
    def _record(self, report, res_ids, content):
        key = ','.join(map(str, sorted(set(res_ids))))
        records = self.env[report.model].browse(sorted(set(res_ids))).exists()
        vals = {
            'report_id': report.id, 'model': report.model, 'res_ids': key,
            'record_name': ', '.join(records.mapped('display_name'))[:250],
        }
        for attempt in range(2):
            vals['copy_no'] = self.search_count([('report_id', '=', report.id), ('res_ids', '=', key)])
            try:
                with self.env.cr.savepoint():
                    log = self.create(vals)
                break
            except IntegrityError:
                if attempt:
                    raise
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
