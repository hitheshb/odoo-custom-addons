import json
import logging
import time

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Message keys we accept from the browser. Anything else is dropped rather
# than forwarded to the provider.
MESSAGE_KEYS = ('role', 'content', 'tool_calls', 'tool_call_id', 'name')

SYSTEM_PROMPT = """You are the assistant built into this Odoo database. You answer \
questions and get work done by calling tools that read and write Odoo records.

How to work:
- You have full access to every model in this database.
- Never guess a technical model name or a field name. Use find_models when you \
are not sure which model holds something, then describe_model to see its fields.
- Never invent record ids. Search first, then act on the ids you found.
- A domain is a list of leaves, e.g. [["state","=","draft"],["partner_id.name","ilike","acme"]]. \
Leaves are ANDed unless you separate them with "&" or "|". An empty list means every record.
- Start with a narrow search (few fields, small limit, a filter that means something) \
and widen only when you find nothing.
- When you create, change or delete records, say which ones by name or id.
- When the user says "this", "here" or "that one", they mean what is on screen - see the screen context below.
- Answer in plain language and keep it short. The user is an Odoo administrator, so \
technical terms are fine.
- Never paste raw JSON back at the user. Turn results into a sentence or a short list.
- If a tool fails, read the error and try another approach instead of repeating the same call.
- If you cannot do something, say so plainly and say why."""

TOOL_LABELS = {
    'delete_records': "Delete",
    'update_records': "Change",
    'create_record': "Create",
    'call_method': "Run",
    'search_records': "Read",
    'count_records': "Count",
    'describe_model': "Looked at fields of",
    'find_models': "Looked for",
}


class ChatbotAgent(models.AbstractModel):
    """The loop: ask the model, run whatever tools it asks for, feed the answers
    back, until it has something to say.

    Yields one event dictionary per thing that happens, so the browser can draw
    the answer as it arrives. The conversation itself lives in the browser, which
    is why a confirmation can simply be sent back as a fresh request.
    """
    _name = 'chatbot.agent'
    _description = 'Chatbot Agent'

    def run(self, messages, screen=None, approvals=None, choice=None):
        llm = self.env['chatbot.llm']
        settings = llm.get_config()
        providers = llm.get_providers(choice)
        if not providers:
            yield {'e': 'error', 'message': _(
                "The chatbot is not set up yet. Add a provider in Settings, Chatbot.")}
            yield {'e': 'done', 'message_id': 0, 'steps': 0, 'state': 'error'}
            return

        tools = self.env['chatbot.tools']
        schemas = tools.schemas()
        approvals = set(approvals or [])
        conversation = self._clean(messages)
        conversation.insert(0, {'role': 'system', 'content': self._system_message(screen)})

        log = self.env['chatbot.message'].create({
            'question': self._last_question(messages),
            'screen_model': (screen or {}).get('model'),
            'screen_res_id': (screen or {}).get('resId') or 0,
            'llm_model': providers[0]['model'],
            'state': 'ok',
        })
        used = providers[0]
        started = time.monotonic()
        steps = 0
        answered = False
        blocked = False
        usage = {}

        try:
            while steps < settings['max_steps']:
                pending = self._pending_calls(conversation)

                if not pending:
                    steps += 1
                    slots = {'spoken': '', 'calls': [], 'usage': {}}
                    for event in self._ask(conversation, schemas, providers, slots):
                        yield event
                    usage = slots['usage']
                    spoken = slots['spoken']
                    pending = slots['calls']
                    if slots.get('config'):
                        used = slots['config']
                        providers = slots.get('providers') or providers
                        log.llm_model = used['model']
                    if not pending:
                        # It answered with words. We are done.
                        conversation.append({'role': 'assistant', 'content': spoken})
                        log.answer = spoken
                        answered = True
                        break
                    assistant_message = {
                        'role': 'assistant',
                        'content': spoken or None,
                        'tool_calls': [self._as_tool_call(call) for call in pending],
                    }
                    conversation.append(assistant_message)
                    # The browser holds the conversation, so it needs the model's
                    # request as well as the results of running it.
                    yield {'e': 'assistant', 'message': assistant_message}

                for call in pending:
                    name, args = self._unpack(call)
                    guarded = tools.is_guarded(name, args)

                    if guarded and call['id'] not in approvals:
                        # Hand it to the user instead of running it. The browser
                        # sends the conversation back with the approval added.
                        self.env['chatbot.tool.call'].create({
                            'message_id': log.id,
                            'name': name,
                            'arguments': json.dumps(args, default=str),
                            'summary': tools.describe_call(name, args),
                            'model_name': args.get('model'),
                            'state': 'waiting',
                            'guarded': True,
                        })
                        log.state = 'waiting'
                        yield {
                            'e': 'confirm',
                            'id': call['id'],
                            'name': name,
                            'args': args,
                            'summary': tools.describe_call(name, args),
                            'records': tools.preview(name, args),
                        }
                        blocked = True
                        break

                    started_call = time.monotonic()
                    try:
                        info = tools.execute(name, args)
                        result = info.pop('result', None)
                        state, problem = 'ok', None
                    except Exception as exc:  # noqa: BLE001 - the model should hear about anything
                        if not isinstance(exc, (UserError, KeyError, ValueError)):
                            _logger.exception("Chatbot tool %s failed", name)
                        info = {
                            'summary': tools.describe_call(name, args),
                            'model_name': args.get('model'),
                            'res_ids': [],
                            'record_count': 0,
                        }
                        result, state, problem = None, 'error', str(exc)

                    tool_message = {
                        'role': 'tool',
                        'tool_call_id': call['id'],
                        'name': name,
                        'content': json.dumps({'error': problem}) if state == 'error'
                                   else tools.render_result(name, info, result),
                    }
                    conversation.append(tool_message)
                    self.env['chatbot.tool.call'].create({
                        'message_id': log.id,
                        'name': name,
                        'arguments': json.dumps(args, default=str),
                        'summary': info['summary'],
                        'model_name': info.get('model_name'),
                        'res_ids': ','.join(str(i) for i in info.get('res_ids') or []),
                        'record_count': info.get('record_count') or 0,
                        'state': state,
                        'guarded': guarded,
                        'duration_ms': int((time.monotonic() - started_call) * 1000),
                    })
                    yield {
                        'e': 'tool',
                        'name': name,
                        'label': TOOL_LABELS.get(name, name),
                        'summary': info['summary'],
                        'state': state,
                        'error': problem,
                        'model': info.get('model_name'),
                        'res_ids': info.get('res_ids') or [],
                        'records': info.get('records') or [],
                        'count': info.get('record_count') or 0,
                        'message': tool_message,
                    }

                if blocked:
                    break
            else:
                yield {'e': 'text', 'd': _(
                    "I stopped after %s steps without finishing. Try asking for "
                    "something narrower.", settings['max_steps'])}
                log.state = 'error'
                log.error = _("Hit the step limit.")
        except UserError as exc:
            log.state = 'error'
            log.error = str(exc)
            yield {'e': 'error', 'message': str(exc)}
        except Exception as exc:  # noqa: BLE001 - never leave the panel hanging
            _logger.exception("The chatbot failed")
            log.state = 'error'
            log.error = str(exc)
            yield {'e': 'error', 'message': str(exc)}
        finally:
            if log.state == 'ok' and not answered:
                log.state = 'error'
                log.error = log.error or _("The assistant did not finish.")
            log.write({
                'step_count': steps,
                'duration_ms': int((time.monotonic() - started) * 1000),
                'prompt_tokens': usage.get('prompt_tokens') or 0,
                'completion_tokens': usage.get('completion_tokens') or 0,
            })

        yield {'e': 'done', 'message_id': log.id, 'steps': steps, 'state': log.state,
               'provider': used['label'], 'model': used['model']}

    # -- pieces of the loop ----------------------------------------------

    def _ask(self, conversation, schemas, providers, slots):
        """One trip to the model, with the backup provider waiting behind it.

        The answer only moves to the next provider while nothing has been said
        yet: once a sentence is on the screen we cannot start again without
        leaving half of it behind."""
        trouble = None
        for position, config in enumerate(providers):
            spoken = False
            slots['spoken'] = ''
            slots['calls'] = []
            slots.pop('config', None)
            try:
                for kind, value in self.env['chatbot.llm'].stream(
                        conversation, tools=schemas, config=config):
                    if kind == 'text':
                        spoken = True
                        slots['spoken'] += value
                        yield {'e': 'text', 'd': value}
                    elif kind == 'tool':
                        slots['calls'] = value
                    elif kind == 'usage' and value:
                        for key in ('prompt_tokens', 'completion_tokens'):
                            slots['usage'][key] = (slots['usage'].get(key) or 0) + (value.get(key) or 0)
                slots['config'] = config
                # Remember who was still standing: the rest of this turn should
                # not keep knocking on a door we already know is shut.
                slots['providers'] = providers[position:]
                return
            except UserError as exc:
                if spoken:
                    raise
                trouble = exc
                following = providers[position + 1] if position + 1 < len(providers) else None
                if not following:
                    break
                _logger.info("Chatbot: %s would not answer (%s), asking %s instead",
                             config['label'], exc, following['label'])
                yield {'e': 'provider', 'key': following['key'], 'label': following['label'],
                       'model': following['model'], 'from': config['label'],
                       'reason': str(exc)[:200]}
        if trouble:
            raise trouble
        raise UserError(_("No provider answered."))

    @staticmethod
    def _pending_calls(conversation):
        """Tool calls the assistant already asked for that have no answer yet.
        Non-empty when the browser comes back after the user approved one."""
        last = conversation[-1]
        if last.get('role') != 'assistant' or not last.get('tool_calls'):
            return []
        answered = {m.get('tool_call_id') for m in conversation if m.get('role') == 'tool'}
        return [{
            'id': call['id'],
            'name': call['function']['name'],
            'arguments': call['function'].get('arguments') or '{}',
            'extra': call.get('extra_content') or {},
        } for call in last['tool_calls'] if call['id'] not in answered]

    @staticmethod
    def _as_tool_call(call):
        """A tool call in the shape it has to be sent back in, signature and all."""
        message = {
            'id': call['id'],
            'type': 'function',
            'function': {'name': call['name'], 'arguments': call['arguments']},
        }
        if call.get('extra'):
            message['extra_content'] = call['extra']
        return message

    @staticmethod
    def _unpack(call):
        name = call.get('name') or ''
        raw = call.get('arguments') or '{}'
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            raise UserError(_(
                "I could not read the arguments the model sent for %(tool)s: %(raw)s",
                tool=name, raw=raw[:300])) from None
        if not isinstance(args, dict):
            raise UserError(_("The model sent arguments in the wrong shape for %s.", name))
        return name, args

    @staticmethod
    def _clean(messages):
        clean = []
        for message in messages or []:
            if not isinstance(message, dict) or not message.get('role'):
                continue
            clean.append({key: value for key, value in message.items() if key in MESSAGE_KEYS})
        return clean

    @staticmethod
    def _last_question(messages):
        for message in reversed(messages or []):
            if message.get('role') == 'user':
                return message.get('content') or ''
        return ''

    def _system_message(self, screen):
        screen = screen or {}
        today = fields.Date.context_today(self.env.user)
        parts = [_(
            "Today is %(date)s. You are talking to %(user)s, in the company %(company)s.",
            date=today, user=self.env.user.name, company=self.env.company.name)]
        model = screen.get('model')
        if model:
            on_screen = _("The user is looking at a %(model)s screen", model=model)
            if screen.get('resId'):
                on_screen += _(", on the record with id %s", screen['resId'])
            parts.append(on_screen + _(
                '. When they say "this" or "here", they mean that record.'))
        else:
            parts.append(_("The user is not on any particular record right now."))
        return f"{SYSTEM_PROMPT}\n\n" + " ".join(parts)
