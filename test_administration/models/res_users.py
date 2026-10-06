from datetime import timedelta

from odoo import api, fields, models
from odoo.http.session import get_session_max_inactivity

ADMIN = 'base.group_system'


class ResUsers(models.Model):
    _inherit = 'res.users'

    idle_timeout = fields.Integer(
        'Idle Timeout (min)', groups=ADMIN,
        help="Log the user out after this many idle minutes. 0 disables it.")
    single_session = fields.Boolean(
        groups=ADMIN, help="A new login logs the user out everywhere else.")
    inactive_alert_days = fields.Integer(
        'Inactivity Alert (days)', groups=ADMIN,
        help="Alert administrators when the user has not logged in for this many days. 0 disables it.")
    admin_last_seen = fields.Datetime('Last Seen', readonly=True, copy=False, groups=ADMIN)
    admin_status = fields.Selection(
        [('online', 'Online'), ('away', 'Away'), ('offline', 'Offline')],
        compute='_compute_admin_status', groups=ADMIN)
    session_count = fields.Integer(compute='_compute_session_count', groups=ADMIN)
    temp_access_ids = fields.One2many('admin.temp.access', 'user_id', groups=ADMIN)

    @api.depends('admin_last_seen')
    def _compute_admin_status(self):
        now = fields.Datetime.now()
        for user in self:
            seen = user.admin_last_seen
            if seen and seen > now - timedelta(minutes=5):
                user.admin_status = 'online'
            elif seen and seen > now - timedelta(minutes=30):
                user.admin_status = 'away'
            else:
                user.admin_status = 'offline'

    def _compute_session_count(self):
        counts = self._admin_session_counts(self.ids)
        for user in self:
            user.session_count = counts.get(user.id, 0)

    @api.model
    def _admin_session_counts(self, user_ids=None):
        limit = fields.Datetime.now() - timedelta(seconds=get_session_max_inactivity(self.env))
        domain = [('last_activity', '>', limit)]
        if user_ids is not None:
            domain.append(('user_id', 'in', user_ids))
        rows = self.env['res.session'].sudo()._read_group(domain, ['user_id'], ['__count'])
        return {user.id: count for user, count in rows}

    def _after_session_login(self):
        super()._after_session_login()
        if self.sudo().single_session:
            self.env['res.session'].sudo().search([('user_id', '=', self.id)])._revoke()

    @api.model
    def _cron_inactive_alert(self):
        Alert = self.env['admin.alert']
        for alert in Alert.search([('resolved', '=', False)]):
            if alert.user_id.login_date and alert.user_id.login_date > alert.create_date:
                alert.resolved = True
        now = fields.Datetime.now()
        new = Alert
        for user in self.search([('inactive_alert_days', '>', 0), ('share', '=', False)]):
            last = user.login_date or user.create_date
            if last > now - timedelta(days=user.inactive_alert_days):
                continue
            if Alert.search_count([('user_id', '=', user.id), ('resolved', '=', False)]):
                continue
            days = (now - last).days
            new |= Alert.create({
                'user_id': user.id,
                'message': self.env._("%(user)s has not logged in for %(days)s days", user=user.name, days=days),
            })
        if new:
            admins = self.search([('group_ids', 'in', self.env.ref(ADMIN).id)]).partner_id
            self.env['mail.thread'].message_notify(
                partner_ids=admins.ids,
                subject=self.env._("Inactive users"),
                body='<br/>'.join(new.mapped('message')),
            )
