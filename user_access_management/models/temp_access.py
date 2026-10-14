from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_datetime


class UserTempAccess(models.Model):
    _name = 'user.temp.access'
    _description = 'Temporary Access'
    _order = 'date_from desc, id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    group_ids = fields.Many2many('res.groups', 'user_temp_access_group_rel', 'access_id', 'group_id',
                                 string='Groups', required=True)
    granted_group_ids = fields.Many2many('res.groups', 'user_temp_access_granted_rel', 'access_id', 'group_id',
                                         string='Groups Added', readonly=True,
                                         help="Groups this record really added (the user did not hold them before).")
    date_from = fields.Datetime('From', required=True, default=fields.Datetime.now)
    date_to = fields.Datetime('Until', required=True)
    state = fields.Selection(
        [('scheduled', 'Scheduled'), ('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled')],
        default='scheduled', readonly=True, index=True)
    note = fields.Char()
    uam_time_left_pct = fields.Integer('Time left', compute='_compute_uam_time_left')
    uam_ending_soon = fields.Boolean(compute='_compute_uam_time_left')

    @api.depends('date_from', 'date_to', 'state')
    def _compute_uam_time_left(self):
        now = fields.Datetime.now()
        for t in self:
            total = (t.date_to - t.date_from).total_seconds() if t.date_to and t.date_from else 0
            left = (t.date_to - now).total_seconds() if t.date_to else 0
            t.uam_time_left_pct = int(max(0, min(100, left * 100 / total))) if total > 0 and t.state == 'active' else 0
            t.uam_ending_soon = t.state == 'active' and 0 < left < 86400

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to <= rec.date_from:
                raise ValidationError(self.env._("'Until' must be after 'From'."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync()
        return records

    def unlink(self):
        self.filtered(lambda r: r.state == 'active')._revoke('cancelled')
        return super().unlink()

    def action_cancel(self):
        self.filtered(lambda r: r.state == 'active')._revoke('cancelled')
        self.filtered(lambda r: r.state == 'scheduled').write({'state': 'cancelled'})

    @api.model
    def _cron_sync(self):
        self.search([('state', 'in', ('scheduled', 'active'))])._sync()

    def _sync(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state == 'scheduled' and rec.date_from <= now:
                if rec.date_to <= now:
                    rec.state = 'expired'
                else:
                    rec._grant()
            elif rec.state == 'active' and rec.date_to <= now:
                rec._revoke('expired')

    def _grant(self):
        self.ensure_one()
        added = self.group_ids - self.user_id.group_ids
        self.user_id.sudo().write({'group_ids': [Command.link(g) for g in added.ids]})
        self.write({'granted_group_ids': [Command.set(added.ids)], 'state': 'active'})

    def _revoke(self, state):
        for rec in self:
            others = self.search([('user_id', '=', rec.user_id.id), ('state', '=', 'active'), ('id', '!=', rec.id)])
            to_remove = rec.granted_group_ids - others.group_ids
            rec.user_id.sudo().write({'group_ids': [Command.unlink(g) for g in to_remove.ids]})
            rec.write({'granted_group_ids': [Command.clear()], 'state': state})

    @api.model
    def uam_my_expiring(self):
        """Caller's own active temporary access (called by every internal user, so never other users' rows)."""
        now = fields.Datetime.now()
        rows = self.sudo().search([('user_id', '=', self.env.uid), ('state', '=', 'active')], order='date_to')
        return [{'id': r.id, 'groups': ', '.join(r.group_ids.mapped('full_name')),
                 'until': format_datetime(self.env, r.date_to),
                 'hours_left': (r.date_to - now).total_seconds() / 3600} for r in rows]
