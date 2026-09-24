from odoo import fields, models, tools


class DispatchReport(models.Model):
    _name = 'hospital.dispatch.report'
    _description = 'Dispatch Report'
    _auto = False
    _order = 'appointment_date desc'
    _rec_name = 'medicine_name'

    # --- from hospital.prescription ---
    medicine_name = fields.Char(string='Medicine', readonly=True)
    dosage = fields.Char(string='Dosage', readonly=True)
    duration = fields.Char(string='Duration', readonly=True)

    # --- from hospital.checkup ---
    temperature = fields.Float(string='Temperature (°F)', readonly=True)
    advice = fields.Text(string='Advice', readonly=True)

    # --- from hospital.appointment ---
    appointment_id = fields.Many2one(
        'hospital.appointment',
        string='Appointment',
        readonly=True,
    )
    appointment_date = fields.Datetime(string='Appointment Date', readonly=True)
    reason = fields.Char(string='Reason for Visit', readonly=True)
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        readonly=True,
    )

    # --- from res.partner (patient) ---
    patient_id = fields.Many2one('res.partner', string='Patient', readonly=True)
    patient_ref = fields.Char(string='Patient ID', readonly=True)
    blood_group = fields.Selection(
        [
            ('a+', 'A+'), ('a-', 'A-'),
            ('b+', 'B+'), ('b-', 'B-'),
            ('ab+', 'AB+'), ('ab-', 'AB-'),
            ('o+', 'O+'), ('o-', 'O-'),
        ],
        string='Blood Group',
        readonly=True,
    )
    age = fields.Integer(string='Age', readonly=True)

    # --- from res.partner (doctor) ---
    doctor_id = fields.Many2one('res.partner', string='Doctor', readonly=True)
    doctor_ref = fields.Char(string='Doctor ID', readonly=True)
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
        readonly=True,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    pr.id               AS id,
                    pr.medicine_name    AS medicine_name,
                    pr.dosage           AS dosage,
                    pr.duration         AS duration,
                    c.temperature       AS temperature,
                    c.advice            AS advice,
                    a.id                AS appointment_id,
                    a.appointment_date  AS appointment_date,
                    a.reason            AS reason,
                    a.status            AS status,
                    pat.id              AS patient_id,
                    pat.patient_ref     AS patient_ref,
                    pat.blood_group     AS blood_group,
                    pat.age             AS age,
                    doc.id              AS doctor_id,
                    doc.doctor_ref      AS doctor_ref,
                    doc.specialization  AS specialization
                FROM hospital_prescription pr
                JOIN hospital_checkup      c   ON c.id   = pr.checkup_id
                JOIN hospital_appointment  a   ON a.id   = c.appointment_id
                JOIN res_partner           pat ON pat.id = a.patient_id
                JOIN res_partner           doc ON doc.id = a.doctor_id
            )
        """ % self._table)
