from collections import defaultdict
from datetime import datetime, time, timedelta

from markupsafe import Markup

from odoo import api, fields, models

GAP = timedelta(minutes=30)


def _monday():
    today = fields.Date.today()
    return today - timedelta(days=today.weekday())


class AdminWeeklySummary(models.TransientModel):
    _name = 'admin.weekly.summary'
    _description = 'Weekly Work Summary'

    week_start = fields.Date(required=True, default=lambda self: _monday())
    user_id = fields.Many2one('res.users', help="Leave empty for everyone.")
    summary_html = fields.Html(compute='_compute_summary_html', sanitize=False)

    @api.depends('week_start', 'user_id')
    def _compute_summary_html(self):
        for wiz in self:
            wiz.summary_html = wiz._build() if wiz.week_start else False

    def _build(self):
        start = datetime.combine(self.week_start, time.min)
        domain = [('create_date', '>=', start), ('create_date', '<', start + timedelta(days=7))]
        if self.user_id:
            domain.append(('user_id', '=', self.user_id.id))
        acts = self.env['admin.activity'].sudo().search(domain, order='create_date')
        if not acts:
            return Markup('<p>No recorded work in this week.</p>')
        names = {m.model: m.name for m in self.env['ir.model'].sudo().search(
            [('model', 'in', list(set(acts.mapped('model_name'))))])}
        tz = lambda dt: fields.Datetime.context_timestamp(self, dt)
        per_user = defaultdict(list)
        for act in acts:
            per_user[act.user_id].append(act)
        out = []
        for user, items in per_user.items():
            out.append(Markup('<h4>%s</h4><ul>') % user.name)
            blocks, cur = [], [items[0]]
            for act in items[1:]:
                same_day = tz(act.create_date).date() == tz(cur[-1].create_date).date()
                if same_day and act.create_date - cur[-1].create_date <= GAP:
                    cur.append(act)
                else:
                    blocks.append(cur)
                    cur = [act]
            blocks.append(cur)
            total = timedelta()
            for block in blocks:
                first, last = tz(block[0].create_date), tz(block[-1].create_date)
                total += last - first
                counts = defaultdict(int)
                for act in block:
                    counts[names.get(act.model_name, act.model_name)] += act.count
                detail = ', '.join(f'{n} ({c})' for n, c in counts.items())
                out.append(Markup('<li>%s %s–%s: %s</li>') % (
                    first.strftime('%a %d %b'), first.strftime('%H:%M'), last.strftime('%H:%M'), detail))
            out.append(Markup('</ul><p>Approx. active time: <b>%.1f h</b></p>') % (total.total_seconds() / 3600))
        return Markup('').join(out)
