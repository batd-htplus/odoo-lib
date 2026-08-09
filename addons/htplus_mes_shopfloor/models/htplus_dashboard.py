from odoo import api, fields, models


class HtplusDashboardKpi(models.Model):
    _inherit = 'htplus.dashboard.kpi'

    qty_good = fields.Float(string='Qty Good', compute='_compute_shopfloor')
    qty_ng = fields.Float(string='Qty NG', compute='_compute_shopfloor')
    yield_pct = fields.Float(string='Yield (%)', compute='_compute_shopfloor')
    downtime_minutes = fields.Float(string='Downtime (minutes)', compute='_compute_shopfloor')
    machine_stop_count = fields.Integer(string='Machine Stops', compute='_compute_shopfloor')
    open_issues = fields.Integer(string='Open Issues', compute='_compute_shopfloor')
    oee_pct = fields.Float(string='OEE (%)', compute='_compute_shopfloor')

    @api.depends('date_from', 'date_to')
    def _compute_shopfloor(self):
        """Compute the shop-floor KPIs for the selected date range."""
        for rec in self:
            window = [
                ('date_start', '>=', fields.Datetime.to_datetime(rec.date_from)),
                ('date_start', '<=', fields.Datetime.to_datetime(rec.date_to) + self._duration_delta()),
            ]
            Actual = self.env['htplus.workorder.actual']
            Downtime = self.env['htplus.downtime']
            Stop = self.env['htplus.machine.stop']
            Issue = self.env['htplus.issue']
            actual_totals = Actual.read_group(window, ['qty_good', 'qty_ng'], [])
            if actual_totals:
                qty_good = actual_totals[0]['qty_good'] or 0.0
                qty_ng = actual_totals[0]['qty_ng'] or 0.0
            else:
                qty_good = qty_ng = 0.0
            rec.qty_good = qty_good
            rec.qty_ng = qty_ng
            rec.yield_pct = qty_good * 100.0 / (qty_good + qty_ng) if (qty_good + qty_ng) else 0.0
            downtime_totals = Downtime.read_group(window, ['duration_minutes'], [])
            if downtime_totals:
                rec.downtime_minutes = downtime_totals[0]['duration_minutes'] or 0.0
            else:
                rec.downtime_minutes = 0.0
            rec.machine_stop_count = Stop.search_count(window)
            rec.open_issues = Issue.search_count([('state', 'in', ('open', 'in_progress'))])
            availability = 1.0 if not rec.downtime_minutes else max(0.0, 1.0 - rec.downtime_minutes / 480.0)
            rec.oee_pct = rec.yield_pct * availability if rec.yield_pct else 0.0

    def _duration_delta(self):
        """Return the delta that extends the search window to cover the whole end date.

        Returns:
            the timedelta to add to date_to.
        """
        from datetime import timedelta
        return timedelta(days=1)

    def action_open_actuals(self):
        """Open the work order execution records.

        Returns:
            the window action listing the actuals.
        """
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.workorder.actual',
            'view_mode': 'tree,form',
            'name': 'Work Order Execution',
        }

    def action_open_downtime(self):
        """Open the downtime records.

        Returns:
            the window action listing downtimes.
        """
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.downtime',
            'view_mode': 'tree,form',
            'name': 'Downtime',
        }

    def action_open_issues(self):
        """Open the issue records.

        Returns:
            the window action listing issues.
        """
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.issue',
            'view_mode': 'tree,form',
            'name': 'Issues',
        }
