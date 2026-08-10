from odoo import api, fields, models, _


class HtplusSystemHealth(models.Model):
    _name = 'htplus.system.health'
    _description = 'System Health'
    _table = 'htplus_system_health'

    name = fields.Char(string='Health', default=lambda self: _('System Health'))
    date_from = fields.Date(default=fields.Date.context_today)
    date_to = fields.Date(default=fields.Date.context_today)

    cron_total = fields.Integer(string='Cron Jobs', compute='_compute_crons')
    cron_active = fields.Integer(string='Active Cron Jobs', compute='_compute_crons')
    cron_overdue = fields.Integer(string='Overdue Cron Jobs', compute='_compute_crons')
    change_count = fields.Integer(string='Schedule Change Logs', compute='_compute_data')
    conflict_count = fields.Integer(string='Schedule Conflicts', compute='_compute_data')
    machine_down = fields.Integer(string='Machines Down', compute='_compute_data')

    alert_summary = fields.Text(string='Alerts', compute='_compute_alert_summary')

    @api.depends('date_from', 'date_to')
    def _compute_crons(self):
        """Aggregate the HTPlus cron jobs: total, active and overdue (nextcall in the past)."""
        now = fields.Datetime.now()
        crons = self.env['ir.cron'].search([
            ('state', '=', 'code'),
            ('model_id.model', 'in', ('htplus.schedule.change', 'htplus.planning.forecast')),
        ])
        for rec in self:
            rec.cron_total = len(crons)
            rec.cron_active = len(crons.filtered('active'))
            rec.cron_overdue = len(crons.filtered(
                lambda c: c.active and (c.nextcall or now) < now))

    @api.depends('date_from', 'date_to')
    def _compute_data(self):
        """Aggregate data-health signals: audit log growth, conflicts and machine downtime."""
        for rec in self:
            rec.change_count = self.env['htplus.schedule.change'].search_count([
                ('date_change', '>=', fields.Datetime.to_string(
                    fields.Datetime.from_string(fields.Date.to_string(rec.date_from) + ' 00:00:00'))),
                ('date_change', '<=', fields.Datetime.to_string(
                    fields.Datetime.from_string(fields.Date.to_string(rec.date_to) + ' 23:59:59'))),
            ])
            rec.conflict_count = self.env['mrp.workorder'].search_count([
                ('schedule_conflict', '=', True),
            ])
            rec.machine_down = self.env['htplus.machine'].search_count([('status', '=', 'down')])

    def _htplus_alert_lines(self):
        """Return the alert lines shown on the health screen.

        HOOK - bridge modules (planning engine, MES, workforce) append their
        own health signals by extending this rather than editing the summary.
        """
        self.ensure_one()
        lines = []
        if self.cron_overdue:
            lines.append(_('%s scheduled cron job(s) overdue (next execution in the past)')
                         % self.cron_overdue)
        if self.conflict_count:
            lines.append(_('%s schedule conflict(s)') % self.conflict_count)
        if self.machine_down:
            lines.append(_('%s machine(s) down') % self.machine_down)
        if self.change_count:
            lines.append(_('%s schedule change log(s) in window') % self.change_count)
        return lines

    @api.depends('cron_overdue', 'conflict_count', 'machine_down', 'change_count')
    def _compute_alert_summary(self):
        """Render the alert lines collected from this module and any bridges."""
        for rec in self:
            lines = rec._htplus_alert_lines()
            rec.alert_summary = '\n'.join(lines) if lines else _('No alerts')

    def action_refresh(self):
        """Invalidate caches so the health screen recomputes its signals."""
        self.invalidate_recordset()
        return True
