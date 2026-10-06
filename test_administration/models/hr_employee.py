from datetime import timedelta

from odoo import fields, models

HR = 'hr.group_hr_user'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    admin_working_now = fields.Boolean('Scheduled Now', compute='_compute_admin_status', groups=HR)
    admin_status = fields.Char('Doing Now', compute='_compute_admin_status', groups=HR)
    admin_last_seen = fields.Datetime(related='user_id.admin_last_seen', groups='base.group_system')

    def _compute_admin_status(self):
        env = self.env
        now = fields.Datetime.now()
        working = set(self.sudo()._get_employee_working_now())
        Activity = env['admin.activity'].sudo()
        for emp in self:
            emp.admin_working_now = emp.id in working
            user = emp.user_id.sudo()
            seen = user.admin_last_seen
            if seen and seen > now - timedelta(minutes=5):
                act = Activity.search([('user_id', '=', user.id), ('create_date', '>', now - timedelta(minutes=15))],
                                      limit=1)
                if act:
                    model = env['ir.model']._get(act.model_name).name or act.model_name
                    mins = int((now - act.create_date).total_seconds() // 60)
                    emp.admin_status = env._("Working on %(model)s (%(mins)s min ago)", model=model, mins=mins)
                else:
                    emp.admin_status = env._("Online, no recent changes")
            elif emp.sudo().attendance_state == 'checked_in':
                emp.admin_status = env._("Checked in, not active in Odoo")
            elif emp.id in working:
                emp.admin_status = env._("Scheduled to work, not active")
            else:
                emp.admin_status = env._("Off hours")
