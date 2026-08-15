from odoo import api, fields, models, _


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
            date_from = fields.Datetime.to_datetime(rec.date_from)
            date_to = fields.Datetime.to_datetime(rec.date_to) + self._duration_delta()
            window = [
                ('date_start', '>=', date_from),
                ('date_start', '<=', date_to),
            ]
            Actual = self.env['htplus.workorder.actual']
            Downtime = self.env['htplus.downtime']
            Stop = self.env['htplus.machine.stop']
            Issue = self.env['htplus.issue']

            actual_rows = Actual.read_group(
                window, ['qty_good:sum', 'qty_ng:sum'], [])
            qty_good = actual_rows[0].get('qty_good') or 0.0 if actual_rows else 0.0
            qty_ng = actual_rows[0].get('qty_ng') or 0.0 if actual_rows else 0.0
            rec.qty_good = qty_good
            rec.qty_ng = qty_ng
            rec.yield_pct = qty_good * 100.0 / (qty_good + qty_ng) if (qty_good + qty_ng) else 0.0

            downtime_rows = Downtime.read_group(
                window, ['duration_minutes:sum'], [])
            rec.downtime_minutes = (
                downtime_rows[0].get('duration_minutes') or 0.0 if downtime_rows else 0.0)
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

    def _dashboard_kpi_cards(self):
        cards = super()._dashboard_kpi_cards()
        cards.extend([
            {'key': 'qty_good', 'label': _('Qty Good'), 'value': self.qty_good, 'tone': 'ok'},
            {'key': 'qty_ng', 'label': _('Qty NG'), 'value': self.qty_ng, 'tone': 'danger'},
            {'key': 'yield_pct', 'label': _('Yield %'), 'value': round(self.yield_pct, 1), 'tone': 'ok'},
            {'key': 'oee_pct', 'label': _('OEE %'), 'value': round(self.oee_pct, 1), 'tone': 'info'},
            {'key': 'downtime_minutes', 'label': _('Downtime (min)'), 'value': self.downtime_minutes, 'tone': 'warn'},
            {'key': 'open_issues', 'label': _('Open Issues'), 'value': self.open_issues, 'tone': 'danger'},
        ])
        return cards

    def _dashboard_charts(self):
        charts = super()._dashboard_charts()
        charts.extend([
            self._chart_quality(),
            self._chart_shopfloor(),
        ])
        return charts

    def _chart_quality(self):
        self.ensure_one()
        has_data = bool(self.qty_good or self.qty_ng)
        return {
            'id': 'quality',
            'title': _('Quality (Good vs NG)'),
            'type': 'doughnut',
            'labels': [_('Good'), _('NG')] if has_data else [_('No data')],
            'datasets': [{
                'data': [self.qty_good or 0.0, self.qty_ng or 0.0] if has_data else [1],
                'backgroundColor': ['#16a34a', '#dc2626'] if has_data else ['#e2e8f0'],
            }],
        }

    def _chart_shopfloor(self):
        self.ensure_one()
        return {
            'id': 'shopfloor',
            'title': _('Shop Floor Signals'),
            'type': 'bar',
            'labels': [_('Downtime min'), _('Machine stops'), _('Open issues')],
            'datasets': [{
                'label': _('Count'),
                'data': [self.downtime_minutes, self.machine_stop_count, self.open_issues],
                'backgroundColor': ['#f59e0b', '#ea580c', '#dc2626'],
            }],
        }

    def _dashboard_shortcuts(self):
        shortcuts = super()._dashboard_shortcuts()
        shortcuts.extend([
            {'key': 'actuals', 'label': _('Actuals')},
            {'key': 'downtime', 'label': _('Downtime')},
            {'key': 'issues', 'label': _('Issues')},
        ])
        return shortcuts

    @api.model
    def get_dashboard_action(self, key, date_from=None, date_to=None, production_plan_id=False):
        if key in ('actuals', 'downtime', 'issues'):
            rec = self._dashboard_record(date_from, date_to, production_plan_id)
            return {
                'actuals': rec.action_open_actuals,
                'downtime': rec.action_open_downtime,
                'issues': rec.action_open_issues,
            }[key]()
        return super().get_dashboard_action(
            key,
            date_from=date_from,
            date_to=date_to,
            production_plan_id=production_plan_id,
        )

    def action_open_actuals(self):
        """Open the shop floor actual records."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.workorder.actual',
            'view_mode': 'list,form',
            'name': _('Shop Floor Actuals'),
        }

    def action_open_downtime(self):
        """Open the downtime records."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.downtime',
            'view_mode': 'list,form',
            'name': _('Downtime'),
        }

    def action_open_issues(self):
        """Open the issue records."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.issue',
            'view_mode': 'list,form',
            'name': _('Issues'),
        }
