import json
import logging
import re
import time
from urllib.parse import urlparse

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai'
# The backup is any OpenAI-shaped provider; OpenRouter is just the pre-filled one
# because its free models make a good safety net behind a throttled Gemini key.
BACKUP_BASE_URL = 'https://openrouter.ai/api/v1'
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 300
# A free key gets throttled (429) and providers have busy moments (503). Both
# usually clear in seconds, so wait and ask again rather than showing an error.
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRIES = 2
RETRY_WAITS = (2, 6)
# A daily quota does not come back in seconds: do not sit there waiting for it.
RETRY_CAP = 60


class ChatbotLLM(models.AbstractModel):
    """Thin client for any provider that speaks the OpenAI chat-completions
    shape: Gemini, OpenRouter, Groq, a local llama.cpp server. Only the base
    URL, the key and the model name change between them."""
    _name = 'chatbot.llm'
    _description = 'Chatbot LLM Client'

    # -- configuration ----------------------------------------------------

    def get_config(self):
        """Everything the client needs, straight from the settings screen."""
        # Odoo 19 renamed ir.config_parameter.get_param/set_param into the typed
        # get_str/get_int/get_float/get_bool and set_* pair.
        params = self.env['ir.config_parameter'].sudo()
        return {
            'key': 'primary',
            'label': self.provider_label(
                params.get_str('chatbot.base_url') or DEFAULT_BASE_URL),
            'base_url': (params.get_str('chatbot.base_url') or DEFAULT_BASE_URL).rstrip('/'),
            'api_key': params.get_str('chatbot.api_key'),
            'model': params.get_str('chatbot.model'),
            'max_steps': params.get_int('chatbot.max_steps', 8),
            'max_tokens': params.get_int('chatbot.max_tokens', 2048),
            'temperature': params.get_float('chatbot.temperature', 0.2),
        }

    def get_backup_config(self):
        """The provider to fall back on. Same shape as the primary one."""
        params = self.env['ir.config_parameter'].sudo()
        return {
            'key': 'backup',
            'label': self.provider_label(
                params.get_str('chatbot.backup_base_url') or BACKUP_BASE_URL),
            'base_url': (params.get_str('chatbot.backup_base_url')
                         or BACKUP_BASE_URL).rstrip('/'),
            'api_key': params.get_str('chatbot.backup_api_key'),
            'model': params.get_str('chatbot.backup_model'),
            'max_steps': params.get_int('chatbot.max_steps', 8),
            'max_tokens': params.get_int('chatbot.max_tokens', 2048),
            'temperature': params.get_float('chatbot.temperature', 0.2),
        }

    def get_providers(self, choice=None):
        """Who to ask, best first: the one the user picked, then the backup.

        A provider only counts if it has both a key and a model, so an untouched
        backup simply never gets tried."""
        providers = [self.get_config(), self.get_backup_config()]
        providers = [item for item in providers if item['api_key'] and item['model']]
        wanted = (choice or {}).get('provider')
        if wanted:
            first = [item for item in providers if item['key'] == wanted]
            if first:
                chosen = dict(first[0])
                model = ((choice or {}).get('model') or '').strip()[:120]
                if model:
                    chosen['model'] = model
                providers = [chosen] + [item for item in providers if item['key'] != wanted]
        return providers

    @staticmethod
    def provider_label(base_url):
        """A short name for a provider, so the panel can say who answered."""
        host = urlparse(base_url or '').netloc.lower()
        for needle, name in (('openrouter', 'OpenRouter'), ('generativelanguage', 'Gemini'),
                             ('googleapis', 'Gemini'), ('groq', 'Groq'),
                             ('openai', 'OpenAI'), ('anthropic', 'Anthropic'),
                             ('localhost', 'Local'), ('127.0.0.1', 'Local')):
            if needle in host:
                return name
        return host or _("the provider")

    def _headers(self, config):
        headers = {'Content-Type': 'application/json'}
        if config['api_key']:
            headers['Authorization'] = f"Bearer {config['api_key']}"
        return headers

    def list_models(self, config=None):
        """The model names the provider offers, for the settings screen."""
        config = config or self.get_config()
        url = f"{config['base_url']}/models"
        try:
            response = requests.get(url, headers=self._headers(config), timeout=CONNECT_TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach %(url)s: %(error)s", url=url, error=exc)) from exc
        if response.status_code >= 400:
            raise UserError(_("The provider refused the request (%(code)s): %(body)s",
                              code=response.status_code, body=response.text[:500]))
        try:
            payload = response.json()
        except ValueError:
            raise UserError(_("%s did not answer with JSON.", url)) from None
        names = []
        for entry in payload.get('data', []):
            name = entry.get('id')
            if not name:
                continue
            # A model that cannot call a function cannot use a single one of our
            # tools, so it is only noise in the list. Providers that say nothing
            # about it keep everything.
            supported = entry.get('supported_parameters')
            if supported and 'tools' not in supported:
                continue
            names.append(name)
        if not names:
            raise UserError(_("No models came back from %s.", url))
        return sorted(names)

    # -- talking to it ----------------------------------------------------

    def stream(self, messages, tools=None, config=None):
        """Call the model once and walk the answer as it arrives.

        Yields ``('text', piece)`` for every fragment of the answer,
        ``('tool', [calls])`` once at the end when it asked for tools, and
        ``('usage', {...})`` when the provider reports token counts.
        """
        config = config or self.get_config()
        url = f"{config['base_url']}/chat/completions"
        payload = {
            'model': config['model'],
            'messages': messages,
            'stream': True,
            'stream_options': {'include_usage': True},
        }
        if config['max_tokens']:
            payload['max_tokens'] = config['max_tokens']
        if config['temperature'] is not None:
            payload['temperature'] = config['temperature']
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'

        try:
            response = self._post_with_retries(url, self._headers(config), payload)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach the model at %(url)s: %(error)s",
                              url=url, error=exc)) from exc

        if response.status_code >= 400:
            raise UserError(
                _("The model refused the request (%(code)s): %(body)s",
                  code=response.status_code, body=response.text[:1000]))

        calls = {}
        usage = None
        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    _logger.warning("Skipping unreadable chunk from the model: %s", data[:200])
                    continue
                if chunk.get('usage'):
                    usage = chunk['usage']
                if chunk.get('error'):
                    raise UserError(_("The model reported: %s", chunk['error']))
                for choice in chunk.get('choices') or []:
                    delta = choice.get('delta') or choice.get('message') or {}
                    text = delta.get('content')
                    if text:
                        yield ('text', text)
                    for call in delta.get('tool_calls') or []:
                        self._collect_call(calls, call)
        except requests.RequestException as exc:
            # A dropped connection counts as the provider not answering, so the
            # agent can hand the question to the backup.
            raise UserError(_("The connection to the model dropped: %(error)s",
                              error=exc)) from exc
        finally:
            response.close()

        ordered = [calls[index] for index in sorted(calls)]
        yield ('tool', ordered)
        if usage:
            yield ('usage', usage)

    @staticmethod
    def _collect_call(calls, fragment):
        """Tool calls arrive in pieces: the name once, the arguments as a JSON
        string split over several chunks. Glue them back together.

        Anything else the provider sent is kept as well: Gemini 3 puts a thought
        signature in ``extra_content`` and refuses the next turn if the call comes
        back without it."""
        index = fragment.get('index', 0)
        call = calls.setdefault(index, {'id': '', 'name': '', 'arguments': '', 'extra': {}})
        if fragment.get('id'):
            call['id'] = fragment['id']
        for vendor, blob in (fragment.get('extra_content') or {}).items():
            call['extra'].setdefault(vendor, {}).update(blob or {})
        function = fragment.get('function') or {}
        name = function.get('name')
        if name and name not in call['name']:
            call['name'] += name
        if function.get('arguments'):
            call['arguments'] += function['arguments']

    @staticmethod
    def _post_with_retries(url, headers, payload):
        """Post, and quietly wait out a throttle or a provider having a bad moment.

        Only safe because nothing has been read from the response yet, so a retry
        cannot repeat half an answer."""
        for attempt in range(RETRIES + 1):
            response = requests.post(
                url, headers=headers, json=payload, stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if response.status_code not in RETRY_STATUS or attempt == RETRIES:
                return response
            wait = ChatbotLLM._wait_before_retry(response, RETRY_WAITS[attempt])
            if wait is None:
                return response
            response.close()
            _logger.info(
                "The model answered %s, waiting %ss and asking again (attempt %s/%s)",
                response.status_code, wait, attempt + 1, RETRIES)
            time.sleep(wait)
        return response

    @staticmethod
    def _wait_before_retry(response, fallback):
        """How long to wait before trying again, or None when waiting is pointless
        because the provider says it will be a long time."""
        seconds = None
        header = (response.headers.get('Retry-After') or '').strip()
        if header.isdigit():
            seconds = int(header)
        else:
            found = re.search(r'retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s',
                              response.text[:2000])
            if found:
                hours, minutes, rest = found.groups()
                seconds = int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(rest or 0)
        if seconds is None:
            return fallback
        return None if seconds > RETRY_CAP else seconds
