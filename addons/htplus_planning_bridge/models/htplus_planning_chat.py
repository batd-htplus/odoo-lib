from odoo import fields, models, _


class HtplusPlanningChat(models.Model):
    _name = 'htplus.planning.chat'
    _description = 'Planning Assistant'

    name = fields.Char(required=True, default=lambda self: _('New'))
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    config_id = fields.Many2one('htplus.planning.config', string='Engine Configuration')
    line_ids = fields.One2many('htplus.planning.chat.line', 'chat_id', string='Messages')
    session_id = fields.Char()

    def _send(self, message, context=None):
        """Send a user message to the planning assistant and store its reply.

        Args:
            message: The user message text.
            context: Optional dict passed to the planning engine.

        Returns:
            The dict response returned by the chat service.
        """
        self.ensure_one()
        if not self.session_id:
            self.session_id = '%s-%s' % (self.id, self.user_id.id)
        self.line_ids = [(0, 0, {'role': 'user', 'content': message})]
        result = self.env['htplus.planning.service'].chat(self.session_id, message, context)
        self.line_ids = [(0, 0, {
            'role': 'assistant',
            'content': result.get('reply', ''),
            'payload': result.get('payload', result),
        })]
        return result


class HtplusPlanningChatLine(models.Model):
    _name = 'htplus.planning.chat.line'
    _description = 'Assistant Message'

    chat_id = fields.Many2one('htplus.planning.chat', required=True, ondelete='cascade')
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ], required=True)
    content = fields.Text(required=True)
    payload = fields.Json(string='Payload')
    created_at = fields.Datetime(default=fields.Datetime.now, string='Created At')
