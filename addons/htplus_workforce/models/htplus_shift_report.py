from odoo import fields, models


class HtplusShiftReportWizard(models.TransientModel):
    _name = 'htplus.shift.report.wizard'
    _description = 'Shift Report'

    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    factory_id = fields.Many2one('htplus.factory', string='Factory')
    line_id = fields.Many2one('htplus.line', string='Line')
    include_completion = fields.Boolean(
        string='Include Shift Completion', default=True,
        help='Also aggregate the MES shift completion records.')

    def _get_domain(self):
        """Build the search domain for the reporting period."""
        self.ensure_one()
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.factory_id:
            domain.append(('factory_id', '=', self.factory_id.id))
        if self.line_id:
            domain.append(('line_id', '=', self.line_id.id))
        return domain

    def _get_lines(self):
        """Aggregate shift actuals into one line per shift.

        Returns:
            List of report line dicts ordered by date and line.
        """
        self.ensure_one()
        actuals = self.env['htplus.shift.actual'].search(
            self._get_domain(), order='date, line_id')
        lines = []
        for actual in actuals:
            lines.append({
                'name': actual.name,
                'date': actual.date,
                'shift': actual.shift_id.display_name or '',
                'line': actual.line_id.name or '',
                'leader': actual.leader_id.name or '',
                'qty_target': actual.qty_target,
                'qty_done': actual.qty_done,
                'qty_good': actual.qty_good,
                'qty_ng': actual.qty_ng,
                'downtime_minutes': actual.downtime_minutes,
                'overtime_minutes': actual.overtime_minutes,
                'manpower_used': actual.manpower_used,
                'achievement_rate': actual.achievement_rate,
                'yield_rate': actual.yield_rate,
            })
        return lines

    def _get_totals(self):
        """Sum the production figures across all report lines."""
        lines = self._get_lines()
        return {
            'qty_target': sum(line['qty_target'] for line in lines),
            'qty_done': sum(line['qty_done'] for line in lines),
            'qty_good': sum(line['qty_good'] for line in lines),
            'qty_ng': sum(line['qty_ng'] for line in lines),
            'downtime_minutes': sum(line['downtime_minutes'] for line in lines),
            'overtime_minutes': sum(line['overtime_minutes'] for line in lines),
            'count': len(lines),
        }

    def action_print_pdf(self):
        """Open the shift report as a PDF."""
        report = self.env.ref('htplus_workforce.action_report_htplus_shift')
        return report.report_action(self)

    def action_export_xlsx(self):
        """Trigger the XLSX export for the selected period."""
        return {
            'type': 'ir.actions.act_url',
            'url': '/htplus/aps/report/shift/export?date_from=%s&date_to=%s&wizard_id=%s'
                   % (self.date_from, self.date_to, self.id),
            'target': 'self',
        }
