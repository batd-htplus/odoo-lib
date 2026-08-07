from odoo import fields, models, _


class HtplusAiChat(models.Model):
    _name = 'htplus.ai.chat'
    _description = 'AI Chat'

    name = fields.Char(required=True, default=lambda self: _('New'))
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    config_id = fields.Many2one('htplus.ai.config', string='AI Configuration')
    line_ids = fields.One2many('htplus.ai.chat.line', 'chat_id', string='Messages')
    session_id = fields.Char()

    def _send(self, message, context=None):
        self.ensure_one()
        if not self.session_id:
            self.session_id = '%s-%s' % (self.id, self.user_id.id)
        self.line_ids = [(0, 0, {'role': 'user', 'content': message})]
        result = self.env['htplus.ai.service'].chat(self.session_id, message, context)
        self.line_ids = [(0, 0, {
            'role': 'assistant',
            'content': result.get('reply', ''),
            'payload': result.get('payload', result),
        })]
        return result


class HtplusAiChatLine(models.Model):
    _name = 'htplus.ai.chat.line'
    _description = 'AI Chat Message'

    chat_id = fields.Many2one('htplus.ai.chat', required=True, ondelete='cascade')
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ], required=True)
    content = fields.Text(required=True)
    payload = fields.Serialized(string='Payload')
    created_at = fields.Datetime(default=fields.Datetime.now, string='Created At')
