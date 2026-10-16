from odoo import _, fields, models

DEFAULT_MODEL = 'gemini-3.5-flash-lite'
BACKUP_MODEL = 'openrouter/free'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatbot_base_url = fields.Char(
        string='API Base URL',
        config_parameter='chatbot.base_url',
        default='https://generativelanguage.googleapis.com/v1beta/openai',
        help="Any provider that speaks the OpenAI chat-completions API. "
             "Gemini: https://generativelanguage.googleapis.com/v1beta/openai, "
             "OpenRouter: https://openrouter.ai/api/v1, Groq: https://api.groq.com/openai/v1.")
    chatbot_api_key = fields.Char(
        string='API Key',
        config_parameter='chatbot.api_key',
        help="Kept on the server and never sent to the browser. The assistant cannot "
             "reach the provider without it.")
    chatbot_model = fields.Selection(
        string='Model',
        selection='_select_chatbot_models',
        config_parameter='chatbot.model',
        default=DEFAULT_MODEL,
        help="Load the provider's model list first, then pick one here. Free models are "
             "slower and clumsier at choosing fields than paid ones.")
    chatbot_backup_base_url = fields.Char(
        string='Backup API Base URL',
        config_parameter='chatbot.backup_base_url',
        default='https://openrouter.ai/api/v1',
        help="The provider to fall back on when the first one will not answer, for "
             "example when its free quota for the day is used up. OpenRouter is the "
             "pre-filled one; any OpenAI-shaped provider works here too.")
    chatbot_backup_api_key = fields.Char(
        string='Backup API Key',
        config_parameter='chatbot.backup_api_key',
        help="Kept on the server, like the main key. Leave empty to have no backup.")
    chatbot_backup_model = fields.Selection(
        string='Backup Model',
        selection='_select_chatbot_backup_models',
        config_parameter='chatbot.backup_model',
        default=BACKUP_MODEL,
        help="Load the backup provider's model list first, then pick one. On OpenRouter "
             "the free models end in :free, and openrouter/free picks one for you.")
    chatbot_max_steps = fields.Integer(
        string='Max Model Calls',
        config_parameter='chatbot.max_steps',
        default=8,
        help="How many times the assistant may go back to the model within one question "
             "before it stops. Each step is one request to the provider.")
    chatbot_max_tokens = fields.Integer(
        string='Max Answer Tokens',
        config_parameter='chatbot.max_tokens',
        default=2048)
    chatbot_temperature = fields.Float(
        string='Temperature',
        config_parameter='chatbot.temperature',
        default=0.2,
        help="Keep this low. The assistant is doing bookkeeping, not writing prose.")

    def _chatbot_choices(self, loaded_key, model_key, default):
        """The options the user can pick from: whatever the provider last told us
        it offers, plus the current one so the field never loses its value."""
        params = self.env['ir.config_parameter'].sudo()
        loaded = params.get_str(loaded_key)
        names = [name.strip() for name in loaded.split(',') if name.strip()]
        current = params.get_str(model_key) or default
        if current not in names:
            names.insert(0, current)
        if not names:
            names = [default]
        return [(name, name) for name in names]

    def _select_chatbot_models(self):
        return self._chatbot_choices('chatbot.loaded_models', 'chatbot.model', DEFAULT_MODEL)

    def _select_chatbot_backup_models(self):
        return self._chatbot_choices('chatbot.backup_loaded_models',
                                     'chatbot.backup_model', BACKUP_MODEL)

    def _chatbot_load_models(self, base_url, api_key, loaded_key):
        """Ask a provider for its model list and remember it for the dropdown."""
        names = self.env['chatbot.llm'].list_models({
            'base_url': (base_url or '').rstrip('/'),
            'api_key': api_key or '',
        })
        self.env['ir.config_parameter'].sudo().set_str(loaded_key, ', '.join(names))
        shown = ', '.join(names[:8])
        more = _(" and %s more", len(names) - 8) if len(names) > 8 else ''
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("%s models available", len(names)),
                'message': f"{shown}{more}",
                'sticky': False,
            },
        }

    def chatbot_load_models(self):
        """Ask the provider for its model list and remember it for the dropdown."""
        self.ensure_one()
        return self._chatbot_load_models(
            self.chatbot_base_url, self.chatbot_api_key, 'chatbot.loaded_models')

    def chatbot_load_backup_models(self):
        """The same, for the provider that answers when the first one will not."""
        self.ensure_one()
        return self._chatbot_load_models(
            self.chatbot_backup_base_url, self.chatbot_backup_api_key,
            'chatbot.backup_loaded_models')
