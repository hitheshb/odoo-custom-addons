from odoo import api, fields, models


class Doctor(models.Model):
    _inherit = 'res.partner'

    is_doctor = fields.Boolean(string='Is Doctor', default=False)
    doctor_ref = fields.Char(string='Doctor ID', readonly=True, copy=False)
    specialization = fields.Selection(
        [
            ('general', 'General Medicine'),
            ('cardiology', 'Cardiology'),
            ('neurology', 'Neurology'),
            ('orthopedics', 'Orthopedics'),
            ('pediatrics', 'Pediatrics'),
            ('dermatology', 'Dermatology'),
        ],
        string='Specialization',
    )
    license_number = fields.Char(string='Medical License Number')
    years_of_experience = fields.Integer(string='Years of Experience')

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner.is_doctor and not partner.doctor_ref:
                partner.doctor_ref = self.env['ir.sequence'].next_by_code('hospital.doctor') or 'New'
        return partners
