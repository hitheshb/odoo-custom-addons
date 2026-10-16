from odoo import SUPERUSER_ID, api, models

SKIP_PREFIXES = ('admin.', 'ir.', 'bus.', 'mail.', 'base.', 'res.users.log', 'res.users.settings',
                 'res.device', 'res.users.apikeys')


class Base(models.AbstractModel):
    _inherit = 'base'

    def _admin_log(self, action, ids=None):
        env = self.env
        if (not self.pool.ready or env.uid == SUPERUSER_ID or self._transient
                or self._name.startswith(SKIP_PREFIXES)
                or env.context.get('install_mode') or env.context.get('module')):
            return
        ids = ids if ids is not None else self.ids
        if not ids:
            return
        try:
            with env.cr.savepoint():
                env['admin.activity'].sudo().create({
                    'user_id': env.uid,
                    'model_name': self._name,
                    'res_id': ids[0],
                    'action': action,
                    'count': len(ids),
                })
        except Exception:
            pass

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._admin_log('create')
        return records

    def write(self, vals):
        res = super().write(vals)
        self._admin_log('write')
        return res

    def unlink(self):
        ids = self.ids
        res = super().unlink()
        self._admin_log('unlink', ids)
        return res
