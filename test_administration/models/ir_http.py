import time

from odoo import fields, models
from odoo.http import request
from odoo.http.session import SessionExpiredException, logout
from odoo.tools import SQL

SKIP_PATHS = ('/websocket', '/bus/', '/longpolling')
TOUCH_EVERY = 30  # seconds between last-seen updates


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        cls._admin_track_activity()

    @classmethod
    def _admin_track_activity(cls):
        session = request.session
        uid = session.uid
        if not uid or request.httprequest.path.startswith(SKIP_PATHS):
            return
        now = time.time()
        last = session.get('admin_last_seen')
        timeout = request.env['res.users'].sudo().browse(uid).idle_timeout
        if timeout and last and now - last > timeout * 60:
            logout(session, keep_db=True)
            raise SessionExpiredException('Logged out after being idle')
        if not last or now - last > TOUCH_EVERY:
            session['admin_last_seen'] = now
            cr = request.env.cr
            if not cr.readonly:
                cr.execute(SQL('UPDATE res_users SET admin_last_seen = %s WHERE id = %s',
                               fields.Datetime.now(), uid))
