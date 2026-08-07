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
        actuals = self.env['htplus.workorder.actual'].search([
            ('date_start', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_start', '<=', fields.Datetime.to_datetime(self.date_to) + self._duration_delta()),
        ])
        downtimes = self.env['htplus.downtime'].search([
            ('date_start', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_start', '<=', fields.Datetime.to_datetime(self.date_to) + self._duration_delta()),
        ])
        stops = self.env['htplus.machine.stop'].search([
            ('date_start', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_start', '<=', fields.Datetime.to_datetime(self.date_to) + self._duration_delta()),
        ])
        issues = self.env['htplus.issue'].search([('state', 'in', ('open', 'in_progress'))])
        for rec in self:
            rec.qty_good = sum(actuals.mapped('qty_good'))
            rec.qty_ng = sum(actuals.mapped('qty_ng'))
            rec.yield_pct = rec.qty_good * 100.0 / (rec.qty_good + rec.qty_ng) if (rec.qty_good + rec.qty_ng) else 0.0
            rec.downtime_minutes = sum(downtimes.mapped('duration_minutes'))
            rec.machine_stop_count = len(stops)
            rec.open_issues = len(issues)
            availability = 1.0 if not rec.downtime_minutes else max(0.0, 1.0 - rec.downtime_minutes / 480.0)
            rec.oee_pct = rec.yield_pct * availability if rec.yield_pct else 0.0

    def _duration_delta(self):
        from datetime import timedelta
        return timedelta(days=1)

    def action_open_actuals(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.workorder.actual',
            'view_mode': 'tree,form',
            'name': 'Work Order Execution',
        }

    def action_open_downtime(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.downtime',
            'view_mode': 'tree,form',
            'name': 'Downtime',
        }

    def action_open_issues(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.issue',
            'view_mode': 'tree,form',
            'name': 'Issues',
        }
