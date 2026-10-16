import json
import logging

from werkzeug.exceptions import BadRequest

from odoo import _, api, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request, route

_logger = logging.getLogger(__name__)

SSE_HEADERS = [
    ('Content-Type', 'text/event-stream; charset=utf-8'),
    ('Cache-Control', 'no-cache, no-store'),
    ('X-Accel-Buffering', 'no'),
]


def _sse(event):
    """One server-sent event. Bytes, so non-latin text goes out unharmed."""
    return f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n".encode()


class ChatbotController(http.Controller):

    def _check_access(self):
        """The assistant runs every tool with sudo, so only administrators may
        talk to it. Checked here rather than in the widget, which anyone could
        bypass by hand."""
        if not request.env.user._is_system():
            raise AccessError(_("The assistant is only available to administrators."))

    @route('/chatbot/state', type='jsonrpc', auth='user')
    def state(self):
        self._check_access()
        llm = request.env['chatbot.llm']
        return {
            'configured': bool(llm.get_providers()),
            'model': llm.get_config()['model'],
        }

    @route('/chatbot/models', type='jsonrpc', auth='user')
    def models(self):
        """What each provider offers, so the panel can list the choices.

        A provider that will not answer is reported with its error instead of
        sinking the whole list: the other one is still worth showing."""
        self._check_access()
        llm = request.env['chatbot.llm']
        providers = []
        for config in (llm.get_config(), llm.get_backup_config()):
            entry = {
                'key': config['key'],
                'label': config['label'],
                'model': config['model'],
                'models': [],
                'error': '',
            }
            if config['api_key'] and config['model']:
                try:
                    names = llm.list_models(config)
                    # The model in use first, then the free ones: a backup
                    # provider is there for when the main one runs out, so its
                    # list should not open on four hundred paid models.
                    names.sort(key=lambda name: (name != config['model'],
                                                 not name.endswith(':free'), name))
                    entry['models'] = names
                except UserError as exc:
                    # The full text is fine in the logs but far too long for a
                    # menu: cut the urllib3 plumbing off the end.
                    message = str(exc)
                    for noise in (' HTTPConnectionPool', ' Max retries exceeded',
                                  ' (Caused by'):
                        message = message.split(noise)[0]
                    entry['error'] = (message.strip(' :')
                                      or _("Could not load the model list."))[:140]
            providers.append(entry)
        return {'providers': providers}

    @route('/chatbot/chat', type='http', auth='user', methods=['POST'], csrf=False)
    def chat(self, **kwargs):
        """Stream one answer back as it is written.

        `csrf=False` because a browser fetch cannot carry Odoo's form token, so
        the token is checked by hand below: without it a hostile page could make
        an administrator's browser rewrite the database."""
        self._check_access()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            raise BadRequest(_("I could not read the request body.")) from None
        if not request.validate_csrf(payload.get('csrf_token')):
            raise BadRequest(_("The session token is missing or stale. Reload the page."))

        # Everything the generator needs is read now: once the response starts
        # going out, `request` is no longer around.
        registry = request.env.registry
        uid = request.env.uid
        env_context = {key: value for key, value in request.env.context.items() if key != 'uid'}
        messages = payload.get('messages') or []
        screen = payload.get('screen') or {}
        approvals = payload.get('approvals') or []
        # Which provider the tab picked. Only ever a key and a model name; the
        # base URL stays on the server.
        choice = payload.get('choice')
        if not isinstance(choice, dict):
            choice = {}

        def generate():
            cursor = registry.cursor()
            try:
                env = api.Environment(cursor, uid, env_context)
                for event in env['chatbot.agent'].run(messages, screen, approvals, choice):
                    yield _sse(event)
                cursor.commit()
            except Exception as exc:  # noqa: BLE001 - the panel must hear about it
                _logger.exception("The chatbot stream failed")
                cursor.rollback()
                yield _sse({'e': 'error', 'message': str(exc)})
                yield _sse({'e': 'done', 'message_id': 0, 'steps': 0, 'state': 'error'})
            finally:
                cursor.close()

        response = request.make_response(generate(), headers=SSE_HEADERS)
        response.direct_passthrough = True
        return response
