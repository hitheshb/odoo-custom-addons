from odoo import api, fields, models


class ChatbotMessage(models.Model):
    """One question and answer of the chat. Written whatever happens, so the
    log shows the failed and refused requests too, not only the happy ones."""
    _name = 'chatbot.message'
    _description = 'Chatbot Question and Answer'
    _order = 'id desc'

    user_id = fields.Many2one(
        'res.users', string='Asked By', required=True, index=True,
        ondelete='cascade', default=lambda self: self.env.user)
    question = fields.Text(required=True)
    answer = fields.Text()
    screen_model = fields.Char(
        string='Screen Model',
        help="Model of the screen the question was asked from.")
    screen_res_id = fields.Integer(string='Screen Record')
    state = fields.Selection(
        selection=[
            ('ok', 'Answered'),
            ('waiting', 'Waiting For Confirmation'),
            ('error', 'Failed'),
        ],
        default='ok', required=True)
    error = fields.Text()
    llm_model = fields.Char(string='Model Used')
    step_count = fields.Integer(string='Model Calls', help="How many times the model was asked.")
    prompt_tokens = fields.Integer()
    completion_tokens = fields.Integer()
    duration_ms = fields.Integer(string='Duration (ms)')
    tool_call_ids = fields.One2many('chatbot.tool.call', 'message_id', string='Tool Calls')
    tool_count = fields.Integer(compute='_compute_tool_count', string='Tools Used')

    @api.depends('tool_call_ids')
    def _compute_tool_count(self):
        for message in self:
            message.tool_count = len(message.tool_call_ids)


class ChatbotToolCall(models.Model):
    """One tool the model asked us to run. This is the record of what the
    assistant actually touched, so a `write` can be traced back to a person."""
    _name = 'chatbot.tool.call'
    _description = 'Chatbot Tool Call'
    _order = 'id'

    message_id = fields.Many2one(
        'chatbot.message', required=True, index=True, ondelete='cascade')
    name = fields.Char(string='Tool', required=True)
    arguments = fields.Text(help="The arguments the model sent, as JSON.")
    summary = fields.Text(help="One line describing what the call did or would do.")
    model_name = fields.Char(string='Model')
    res_ids = fields.Char(string='Records', help="Comma separated record ids the call touched.")
    record_count = fields.Integer(string='Record Count')
    state = fields.Selection(
        selection=[
            ('ok', 'Done'),
            ('error', 'Failed'),
            ('denied', 'Refused'),
            ('waiting', 'Waiting For Confirmation'),
        ],
        default='ok', required=True)
    guarded = fields.Boolean(
        string='Needed Confirmation',
        help="Set when the call was destructive or touched framework models, so it "
             "was shown to the user before running.")
    duration_ms = fields.Integer(string='Duration (ms)')
