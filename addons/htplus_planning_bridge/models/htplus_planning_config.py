import secrets

from odoo import fields, models


class HtplusPlanningConfig(models.Model):
    _name = 'htplus.planning.config'
    _description = 'Planning Engine Configuration'
    _check_company_auto = True

    name = fields.Char(required=True)
    url = fields.Char(string='Service URL', required=True, help='Base URL of the planning engine.')
    api_key = fields.Char(string='API Key', groups='base.group_system',
                          default=lambda self: secrets.token_urlsafe(32))
    model = fields.Char(default='default')
    timeout_sec = fields.Integer(string='Timeout (seconds)', default=30)
    retry_max = fields.Integer(string='Max Retries', default=3,
                               help='How many times to retry a request after a transient error.')
    retry_backoff = fields.Float(string='Retry Backoff (s)', default=1.0,
                                 help='Base delay before the first retry; doubles after each attempt.')
    log_requests = fields.Boolean(string='Log Requests', default=True,
                                  help='Record every engine call in the request log.')
    circuit_failure_threshold = fields.Integer(string='Failure Threshold', default=3,
                                               help='Consecutive failures that trip the circuit breaker open.')
    circuit_recovery_timeout = fields.Integer(string='Recovery Timeout (s)', default=60,
                                              help='Wait before allowing a trial request after a trip.')
    circuit_state = fields.Selection([
        ('closed', 'Closed'),
        ('half_open', 'Half Open'),
        ('open', 'Open'),
    ], string='Circuit State', default='closed', readonly=True,
        help='Closed = normal calls. Open = engine considered down, calls are refused. Half Open = single trial.')
    circuit_failures = fields.Integer(string='Consecutive Failures', default=0, readonly=True)
    circuit_open_since = fields.Datetime(string='Opened At', readonly=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The planning engine configuration name must be unique.'),
    ]

    def _get_active(self):
        """Return the active planning engine configuration for the current company."""
        company = self.env.company
        return self.search([
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)

    def _circuit_record_success(self):
        """Close the circuit and reset the failure counter after a successful call."""
        if self.circuit_state != 'closed' or self.circuit_failures:
            self.write({'circuit_state': 'closed', 'circuit_failures': 0, 'circuit_open_since': False})

    def _circuit_record_failure(self):
        """Count a failure and open the circuit once the threshold is reached.

        A failure while half-open (a trial request) re-opens immediately.
        """
        if self.circuit_state == 'open':
            return
        if self.circuit_state == 'half_open':
            self.write({'circuit_state': 'open', 'circuit_failures': self.circuit_failure_threshold,
                        'circuit_open_since': fields.Datetime.now()})
            return
        failures = self.circuit_failures + 1
        if failures >= self.circuit_failure_threshold:
            self.write({'circuit_failures': failures, 'circuit_state': 'open',
                        'circuit_open_since': fields.Datetime.now()})
        else:
            self.write({'circuit_failures': failures})

    def _circuit_allows(self):
        """Return True when the circuit allows a request, tripping to half-open if recovery time passed."""
        if self.circuit_state != 'open':
            return True
        opened = self.circuit_open_since or fields.Datetime.now()
        if fields.Datetime.now() >= fields.Datetime.add(opened, seconds=self.circuit_recovery_timeout):
            self.write({'circuit_state': 'half_open'})
            return True
        return False

    def action_reset_circuit(self):
        """Manually close the circuit breaker and clear the failure counter."""
        self._circuit_record_success()
