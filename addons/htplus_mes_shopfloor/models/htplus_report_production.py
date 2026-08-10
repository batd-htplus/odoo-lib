from odoo import fields, models


class HtplusReportProductionDaily(models.TransientModel):
    _name = 'htplus.report.production.daily'
    _description = 'Daily Production Report'

    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    def _get_lines(self):
        """Build report lines grouping actuals and downtimes by work order.

        Returns:
            the list of report line dicts.
        """
        self.ensure_one()
        lines = []
        actuals = self.env['htplus.workorder.actual'].search([
            ('date_start', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_start', '<=', fields.Datetime.to_datetime(self.date_to) + fields.timedelta(days=1)),
        ])
        grouped = {}
        for actual in actuals:
            key = (actual.workorder_id.id, actual.workorder_id.workcenter_id.id, actual.workorder_id.machine_id.id)
            bucket = grouped.setdefault(key, {
                'workorder': actual.workorder_id.display_name,
                'workcenter': actual.workorder_id.workcenter_id.name,
                'machine': actual.workorder_id.machine_id.name or '',
                'qty_good': 0.0,
                'qty_ng': 0.0,
                'downtime_minutes': 0.0,
            })
            bucket['qty_good'] += actual.qty_good
            bucket['qty_ng'] += actual.qty_ng
        downtimes = self.env['htplus.downtime'].search([
            ('date_start', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_start', '<=', fields.Datetime.to_datetime(self.date_to) + fields.timedelta(days=1)),
        ])
        for downtime in downtimes:
            key = (downtime.workorder_id.id, downtime.workorder_id.workcenter_id.id, downtime.workorder_id.machine_id.id)
            if key in grouped:
                grouped[key]['downtime_minutes'] += downtime.duration_minutes
        for key in sorted(grouped):
            lines.append(grouped[key])
        return lines

    def _get_totals(self):
        """Sum the production figures across all report lines.

        Returns:
            the totals dict for the report.
        """
        lines = self._get_lines()
        return {
            'qty_good': sum(line['qty_good'] for line in lines),
            'qty_ng': sum(line['qty_ng'] for line in lines),
            'downtime_minutes': sum(line['downtime_minutes'] for line in lines),
        }

    def action_print_pdf(self):
        """Open the daily production report as a PDF.

        Returns:
            the report action.
        """
        report = self.env.ref('htplus_mes_shopfloor.action_report_htplus_production_daily')
        return report.report_action(self)

    def action_export_xlsx(self):
        """Trigger the XLSX export for the selected period.

        Returns:
            the URL action to download the file.
        """
        return {
            'type': 'ir.actions.act_url',
            'url': '/htplus/mes/report/production/export?date_from=%s&date_to=%s&wizard_id=%s'
                   % (self.date_from, self.date_to, self.id),
            'target': 'self',
        }
