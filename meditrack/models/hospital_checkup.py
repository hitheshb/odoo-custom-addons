from odoo import api, fields, models


class Checkup(models.Model):
    _name = 'hospital.checkup'
    _description = 'Check-up'
    _rec_name = "appointment_id"

    appointment_id = fields.Many2one(
        'hospital.appointment',
        string='Appointment',
        required=True,
        ondelete='cascade',
    )
    temperature = fields.Float(string='Temperature (°F)')
    advice = fields.Text(string='Advice')
    prescription_ids = fields.One2many(
        'hospital.prescription',
        'checkup_id',
        string='Prescriptions',
    )

    @api.model_create_multi
    def create(self, vals_list):
        checkups = super().create(vals_list)
        checkups.appointment_id.write({'status': 'done'})
        return checkups
