from odoo import fields, models


class HtplusPlanningRequestLog(models.Model):
    _name = 'htplus.planning.request.log'
    _description = 'Planning Engine Request Log'
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    config_id = fields.Many2one('htplus.planning.config', string='Engine Configuration',
                                ondelete='set null', check_company=True)
    endpoint = fields.Char(string='Endpoint')
    method = fields.Selection([
        ('post', 'POST'),
        ('get', 'GET'),
    ], string='Method', default='post')
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Status')
    status_code = fields.Integer(string='HTTP Status')
    error = fields.Text(string='Error')
    response_time_ms = fields.Integer(string='Response Time (ms)')
    retries = fields.Integer(string='Retries', default=0)
    idempotency_key = fields.Char(string='Idempotency Key')
    request_payload = fields.Json(string='Request Payload')
    response = fields.Json(string='Response')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def _log(self, config, **kwargs):
        """Create a request log entry without raising on failure.

        Args:
            config: The htplus.planning.config record the call was made against.
        """
        if not config.log_requests:
            return self.env['htplus.planning.request.log']
        vals = {key: value for key, value in kwargs.items() if value is not None}
        try:
            return self.sudo().create(vals)
        except Exception:
            _logger = __import__('logging').getLogger(__name__)
            _logger.exception('Failed to write planning request log')
            return self.env['htplus.planning.request.log']
