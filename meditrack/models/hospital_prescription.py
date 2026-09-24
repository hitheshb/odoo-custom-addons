from odoo import fields, models


class Prescription(models.Model):
    _name = 'hospital.prescription'
    _description = 'Prescription'

    checkup_id = fields.Many2one(
        'hospital.checkup',
        string='Check-up',
        required=True,
        ondelete='cascade',
    )
    medicine_name = fields.Char(string='Medicine', required=True)
    dosage = fields.Char(string='Dosage')
    duration = fields.Char(string='Duration')
    notes = fields.Text(string='Notes')
