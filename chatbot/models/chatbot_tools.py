import json
import logging
import time

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_ROWS = 200
MAX_RESULT_CHARS = 8000
MAX_SELECTION_VALUES = 40

# Records the assistant must ask about before it writes or deletes them: the
# framework the database itself runs on, plus the three models that decide who
# can do what. Everything else is ordinary business data and goes straight
# through.
PROTECTED_MODELS = {'res.users', 'res.groups', 'res.company'}
PROTECTED_PREFIXES = ('ir.', 'base.')

TOOL_SCHEMAS = [
    {
        'type': 'function',
        'function': {
            'name': 'find_models',
            'description': "Search the list of Odoo models (tables) by a keyword. "
                           "Use this whenever you are not sure of the technical model name.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': "Keyword such as 'invoice', 'leave' or 'stock'."},
                    'limit': {'type': 'integer', 'description': 'How many models to return. Default 15.'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'describe_model',
            'description': "List the fields of a model: name, type, label, whether required, and the "
                           "target model for relational fields. Call this before searching or writing "
                           "on a model you do not know by heart.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string', 'description': "Technical model name, e.g. 'sale.order'."},
                    'fields': {
                        'type': 'array', 'items': {'type': 'string'},
                        'description': 'Only describe these field names. Omit to describe every field.',
                    },
                },
                'required': ['model'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_records',
            'description': 'Read records. Returns a list of rows.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string', 'description': 'Technical model name.'},
                    'domain': {
                        'type': 'array',
                        'description': 'Odoo domain: a list of leaves, e.g. '
                                       '[["state","=","draft"],["partner_id.name","ilike","acme"]]. '
                                       'An empty list means every record.',
                        'items': {'type': 'array'},
                    },
                    'fields': {
                        'type': 'array', 'items': {'type': 'string'},
                        'description': 'Field names to read. Omit for every field.',
                    },
                    'limit': {'type': 'integer', 'description': 'Maximum rows. Default 20, capped at 200.'},
                    'order': {'type': 'string', 'description': "Sort order such as 'date_order desc'."},
                },
                'required': ['model'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'count_records',
            'description': 'Count how many records match a domain. Cheaper than search_records when you '
                           'only need a number.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string'},
                    'domain': {'type': 'array', 'items': {'type': 'array'}},
                },
                'required': ['model'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'create_record',
            'description': 'Create one record. Returns its id.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string'},
                    'values': {
                        'type': 'object',
                        'description': 'Field name to value. Use ids for relational fields, and '
                                       'command lists such as [[0,0,{...}]] for one2many.',
                    },
                },
                'required': ['model', 'values'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'update_records',
            'description': 'Change existing records. Search first to get the ids.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string'},
                    'ids': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'Record ids to change.'},
                    'values': {'type': 'object', 'description': 'Field name to new value.'},
                },
                'required': ['model', 'ids', 'values'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'delete_records',
            'description': 'Permanently delete records. There is no undo. The user is asked to confirm '
                           'before this runs.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string'},
                    'ids': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'Record ids to delete.'},
                },
                'required': ['model', 'ids'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'call_method',
            'description': 'Call a public method on records, for the work that is not a plain field write, '
                           "such as 'action_post' on an invoice or 'action_confirm' on a sale order. "
                           'Private methods (names starting with _) are refused.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'model': {'type': 'string'},
                    'method': {'type': 'string', 'description': 'Public method name.'},
                    'ids': {'type': 'array', 'items': {'type': 'integer'}},
                    'kwargs': {'type': 'object', 'description': 'Keyword arguments for the method.'},
                },
                'required': ['model', 'method'],
            },
        },
    },
]


def _is_protected(model_name):
    return bool(model_name) and (
        model_name in PROTECTED_MODELS or model_name.startswith(PROTECTED_PREFIXES)
    )


# The tools the model is allowed to ask for, taken from the schemas themselves
# so the two can never drift apart.
TOOL_NAMES = frozenset(
    schema['function']['name'] for schema in TOOL_SCHEMAS
)


def _normalise_domain(domain):
    """Accept the domain as the model sent it. JSON turns every leaf into a
    list, which is fine either way, but a string is a common slip."""
    if domain in (None, '', []):
        return []
    if isinstance(domain, str):
        try:
            domain = json.loads(domain)
        except ValueError:
            raise UserError(_("The domain is not valid JSON: %s", domain)) from None
    if not isinstance(domain, list):
        raise UserError(_("The domain must be a list, got: %r", domain))
    return [tuple(leaf) if isinstance(leaf, list) else leaf for leaf in domain]


def _jsonable(value, depth=0):
    """Turn whatever a method returned into something we can put in a message."""
    if depth > 4:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth + 1) for key, item in value.items()}
    if hasattr(value, 'ids'):  # a recordset
        names = value.read(['display_name']) if value else []
        return [{'id': row['id'], 'name': row['display_name']} for row in names]
    return str(value)


def _truncate(text):
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + _(" ...(truncated)")


class ChatbotTools(models.AbstractModel):
    """The Odoo operations the model is allowed to ask for. Every call runs with
    sudo, which is why only administrators get to chat at all - see the
    controller."""
    _name = 'chatbot.tools'
    _description = 'Odoo Tools For The Chatbot'

    # -- what the model may call ------------------------------------------

    def schemas(self):
        return TOOL_SCHEMAS

    def is_guarded(self, name, args):
        """True when the user should see this call before it happens."""
        args = args or {}
        if name == 'delete_records':
            return True
        if name == 'call_method' and str(args.get('method') or '').startswith('unlink'):
            return True
        return _is_protected(args.get('model')) and name in (
            'create_record', 'update_records', 'call_method')

    def describe_call(self, name, args):
        args = args or {}
        model = args.get('model') or ''
        count = len(args.get('ids') or [])
        if name == 'delete_records':
            return _("Delete %(count)s record(s) from %(model)s", count=count, model=model)
        if name == 'create_record':
            return _("Create a record in %s", model)
        if name == 'update_records':
            return _("Change %(count)s record(s) in %(model)s", count=count, model=model)
        if name == 'call_method':
            return _("Run %(method)s on %(count)s %(model)s record(s)",
                     method=args.get('method') or '', count=count, model=model)
        return name

    def preview(self, name, args, limit=5):
        """The records a guarded call would touch, so the user can see what is
        about to happen instead of a bare count."""
        args = args or {}
        model_name = args.get('model')
        ids = args.get('ids') or []
        if not model_name or not ids or model_name not in self.env:
            return []
        try:
            model = self.env[model_name].sudo()
        except KeyError:
            return []
        rows = model.browse([int(i) for i in ids[:limit]]).exists().read(['display_name'])
        return [{'id': row['id'], 'name': row['display_name']} for row in rows]

    # -- running them -----------------------------------------------------

    def execute(self, name, args):
        """Run one tool. Returns the `result` handed back to the model plus the
        bits we log about the call."""
        if name not in TOOL_NAMES:
            raise UserError(_("Unknown tool: %s", name))
        started = time.monotonic()
        result = getattr(self, f'_run_{name}')(args or {})
        info = self._describe_result(name, args or {}, result)
        info['duration_ms'] = int((time.monotonic() - started) * 1000)
        info['result'] = result
        return info

    def _model(self, args):
        model_name = args.get('model')
        if not model_name:
            raise UserError(_("No model given."))
        if model_name not in self.env:
            raise UserError(_("There is no model called '%s' in this database.", model_name))
        # sudo: the assistant is promised full access, and only administrators
        # can reach it.
        return self.env[model_name].sudo()

    def _run_find_models(self, args):
        query = (args.get('query') or '').strip()
        limit = min(int(args.get('limit') or 15), 60)
        if not query:
            raise UserError(_("Give me something to search for."))
        # Search the label as well as the technical name: "invoices" finds
        # account.move through its description.
        records = self.env['ir.model'].sudo().search_read(
            ['|', ('model', 'ilike', query), ('name', 'ilike', query)],
            ['model', 'name'], limit=limit, order='model')
        return [{'model': row['model'], 'name': row['name']} for row in records]

    def _run_describe_model(self, args):
        model = self._model(args)
        wanted = args.get('fields') or None
        fields = model.fields_get(wanted, attributes=[
            'string', 'type', 'required', 'readonly', 'relation', 'selection', 'store'])
        described = {}
        for fname, info in fields.items():
            entry = {
                'type': info.get('type'),
                'label': info.get('string'),
            }
            if info.get('required'):
                entry['required'] = True
            if info.get('readonly'):
                entry['readonly'] = True
            if info.get('type') == 'many2one' or info.get('relation'):
                entry['target'] = info.get('relation')
            selection = info.get('selection')
            if selection:
                pairs = [(value, label) for value, label in selection][:MAX_SELECTION_VALUES]
                entry['values'] = [f"{value} ({label})" for value, label in pairs]
            described[fname] = entry
        return {
            'model': model._name,
            'label': model._description,
            'field_count': len(described),
            'fields': dict(sorted(described.items())),
        }

    def _run_search_records(self, args):
        model = self._model(args)
        domain = _normalise_domain(args.get('domain'))
        fields = args.get('fields') or None
        if fields and 'id' not in fields:
            fields = ['id', *fields]
        limit = min(int(args.get('limit') or 20), MAX_ROWS)
        rows = model.search_read(domain, fields, limit=limit, order=args.get('order') or None)
        return {'count': len(rows), 'rows': rows}

    def _run_count_records(self, args):
        model = self._model(args)
        return {'count': model.search_count(_normalise_domain(args.get('domain')))}

    def _run_create_record(self, args):
        model = self._model(args)
        record = model.create(args.get('values') or {})
        return {'created': {'id': record.id, 'name': record.display_name}}

    def _run_update_records(self, args):
        model = self._model(args)
        ids = [int(i) for i in (args.get('ids') or [])]
        if not ids:
            raise UserError(_("Which records should I change? I need their ids."))
        records = model.browse(ids).exists()
        records.write(args.get('values') or {})
        return {'changed': len(records), 'records': self._names(records)}

    def _run_delete_records(self, args):
        model = self._model(args)
        ids = [int(i) for i in (args.get('ids') or [])]
        if not ids:
            raise UserError(_("Which records should I delete? I need their ids."))
        records = model.browse(ids).exists()
        gone = self._names(records)
        records.unlink()
        return {'deleted': len(gone), 'records': gone}

    def _run_call_method(self, args):
        model = self._model(args)
        method_name = args.get('method') or ''
        if not method_name or method_name.startswith('_'):
            raise UserError(_("'%s' is not a method I am allowed to call.", method_name))
        ids = [int(i) for i in (args.get('ids') or [])]
        records = model.browse(ids)
        method = getattr(records, method_name, None)
        if method is None or not callable(method):
            raise UserError(_("Model '%(model)s' has no method called '%(method)s'.",
                              model=model._name, method=method_name))
        outcome = method(**(args.get('kwargs') or {}))
        result = _jsonable(outcome)
        if result is None:
            result = {'called': method_name, 'records': self._names(records)}
        return result

    def _names(self, records):
        if not records:
            return []
        return [{'id': row['id'], 'name': row['display_name']}
                for row in records.read(['display_name'])]

    def _describe_result(self, name, args, result):
        """What we show in the chat and write to the log about this call."""
        model_name = args.get('model')
        res_ids = []
        count = 0
        records = []
        if name == 'search_records':
            count = result.get('count', 0)
            res_ids = [row.get('id') for row in result.get('rows', []) if row.get('id')]
        elif name == 'count_records':
            count = result.get('count', 0)
        elif name == 'find_models':
            count = len(result)
            model_name = None
        elif name == 'create_record':
            created = result.get('created') or {}
            res_ids = [created['id']] if created.get('id') else []
            count = len(res_ids)
            records = [{'id': created['id'], 'name': created.get('name')}] if res_ids else []
        elif name == 'describe_model':
            count = result.get('field_count', 0)
        else:
            for key in ('changed', 'deleted'):
                if key in result:
                    count = result[key]
            records = [row for row in result.get('records', []) if isinstance(row, dict)]
            res_ids = [row['id'] for row in records]
        if not records and model_name and res_ids and name != 'delete_records':
            try:
                records = self._names(self.env[model_name].sudo().browse(res_ids[:5]))
            except KeyError:
                records = []
        summary = self.describe_call(name, args)
        if count:
            summary = f"{summary} -> {count}"
        return {
            'summary': summary,
            'model_name': model_name,
            'res_ids': res_ids,
            'records': records,
            'record_count': count,
        }

    def render_result(self, name, info, result):
        """The text handed back to the model. Trimmed, because a wide read can
        be enormous and every token costs the user time."""
        return _truncate(json.dumps({'summary': info['summary'], 'result': result},
                                    default=str, ensure_ascii=False))
