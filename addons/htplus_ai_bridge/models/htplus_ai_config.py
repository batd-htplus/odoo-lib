from odoo import fields, models


class HtplusAiConfig(models.Model):
    _name = 'htplus.ai.config'
    _description = 'AI Service Configuration'

    name = fields.Char(required=True)
    url = fields.Char(string='Service URL', required=True, help='Base URL of the AI service.')
    api_key = fields.Char(string='API Key', password=True)
    model = fields.Char(default='default')
    timeout_sec = fields.Integer(string='Timeout (seconds)', default=30)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The AI configuration name must be unique.'),
    ]

    def _get_active(self):
        return self.search([('active', '=', True)], limit=1)
