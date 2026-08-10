from datetime import timedelta

from odoo import api, fields, models, _


class HtplusSystemHealth(models.Model):
    _inherit = 'htplus.system.health'

    engine_state = fields.Char(string='Engine Circuit', compute='_compute_engine')
    engine_failures = fields.Integer(string='Engine Failures', compute='_compute_engine')
    engine_open_since = fields.Datetime(string='Circuit Opened At', compute='_compute_engine')
    engine_req_total = fields.Integer(string='Engine Requests (24h)', compute='_compute_engine')
    engine_req_ok = fields.Integer(string='Succeeded (24h)', compute='_compute_engine')
    engine_req_failed = fields.Integer(string='Failed (24h)', compute='_compute_engine')
    engine_req_skipped = fields.Integer(string='Skipped (24h)', compute='_compute_engine')
    engine_avg_ms = fields.Integer(string='Avg Response (ms)', compute='_compute_engine')
    engine_last_error = fields.Text(string='Last Engine Error', compute='_compute_engine')
    forecast_stuck = fields.Integer(string='Stuck Forecasts', compute='_compute_engine')

    @api.depends('date_from', 'date_to')
    def _compute_engine(self):
        """Aggregate planning-engine health signals from the config and request log."""
        since = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=24)
        log_model = 'htplus.planning.request.log'
        for rec in self:
            config = self.env['htplus.planning.config']._get_active()
            rec.engine_state = config.circuit_state if config else 'no_config'
            rec.engine_failures = config.circuit_failures if config else 0
            rec.engine_open_since = config.circuit_open_since if config else False
            Log = self.env[log_model]
            rec.engine_req_total = Log.search_count([('create_date', '>=', since)])
            rec.engine_req_ok = Log.search_count(
                [('create_date', '>=', since), ('status', '=', 'success')])
            rec.engine_req_failed = Log.search_count(
                [('create_date', '>=', since), ('status', '=', 'failed')])
            rec.engine_req_skipped = Log.search_count(
                [('create_date', '>=', since), ('status', '=', 'skipped')])
            avg = Log.read_group(
                [('create_date', '>=', since), ('status', '=', 'success')],
                ['response_time_ms:avg'], [])
            rec.engine_avg_ms = int(avg[0]['response_time_ms'] or 0) if avg else 0
            last_failed = Log.search(
                [('status', '=', 'failed')], limit=1, order='create_date desc')
            rec.engine_last_error = last_failed.error if last_failed else False
            stuck_cutoff = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=1)
            rec.forecast_stuck = self.env['htplus.planning.forecast'].search_count([
                ('state', '=', 'draft'),
                ('job_id', '!=', False),
                ('create_date', '<', stuck_cutoff),
            ])

    def _htplus_alert_lines(self):
        """Append planning-engine health alerts to the core summary."""
        self.ensure_one()
        lines = super()._htplus_alert_lines()
        if self.engine_state == 'open':
            lines.append(_('Planning engine circuit breaker OPEN (since %s)') % (
                fields.Datetime.to_string(self.engine_open_since) if self.engine_open_since else '?'
            ))
        elif self.engine_state == 'half_open':
            lines.append(_('Planning engine circuit HALF OPEN — trial request'))
        elif self.engine_state == 'no_config':
            lines.append(_('No active planning engine configuration'))
        if self.engine_req_failed:
            lines.append(_('%s planning engine request(s) failed in the last 24h')
                         % self.engine_req_failed)
        if self.forecast_stuck:
            lines.append(_('%s forecast(s) stuck on a pending engine job')
                         % self.forecast_stuck)
        return lines

    @api.depends(
        'engine_state', 'engine_req_failed', 'forecast_stuck',
        'cron_overdue', 'conflict_count', 'machine_down', 'change_count',
    )
    def _compute_alert_summary(self):
        """Re-render the alert summary with the bridge health signals included."""
        for rec in self:
            lines = rec._htplus_alert_lines()
            rec.alert_summary = '\n'.join(lines) if lines else _('No alerts')
