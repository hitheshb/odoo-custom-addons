from odoo import api, fields, models


class Patient(models.Model):
    _inherit = 'res.partner'

    is_patient = fields.Boolean(string='Is Patient', default=False)
    patient_ref = fields.Char(string='Patient ID', readonly=True, copy=False)
    date_of_birth = fields.Date(string='Date of Birth')
    blood_group = fields.Selection(
        [
            ('a+', 'A+'), ('a-', 'A-'),
            ('b+', 'B+'), ('b-', 'B-'),
            ('ab+', 'AB+'), ('ab-', 'AB-'),
            ('o+', 'O+'), ('o-', 'O-'),
        ],
        string='Blood Group',
    )

    age = fields.Integer(string='Age', compute='_compute_age', store = True)

    @api.depends('date_of_birth')
    def _compute_age(self):
        for patient in self:
            if patient.date_of_birth:
                today = fields.Date.today()
                patient.age = today.year - patient.date_of_birth.year - (
                    (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
                )
            else:
                patient.age = 0


    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner.is_patient and not partner.patient_ref:
                partner.patient_ref = self.env['ir.sequence'].next_by_code('hospital.patient') or 'New'
        return partners
