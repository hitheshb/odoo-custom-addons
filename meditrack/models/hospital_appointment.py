from odoo import api, fields, models


class Appointment(models.Model):
    _name = 'hospital.appointment'
    _description = 'Appointment'

    name = fields.Char(string='Reference', default='New', readonly=True, copy=False)
    patient_id = fields.Many2one(
        'res.partner',
        string='Patient',
        domain=[('is_patient', '=', True)],
        required=True,
    )
    doctor_id = fields.Many2one(
        'res.partner',
        string='Doctor',
        domain=[('is_doctor', '=', True)],
        required=True,
    )
    appointment_date = fields.Datetime(string='Appointment Date', required=True)
    reason = fields.Char(string='Reason for Visit')
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hospital.appointment') or 'New'
        return super().create(vals_list)

    @api.onchange('appointment_date')
    def _onchange_appointment_date(self):
        if self.appointment_date and self.appointment_date < fields.Datetime.now():
            return {
                'warning': {
                    'title': 'Past date',
                    'message': 'The selected appointment date is in the past.',
                }
            }

