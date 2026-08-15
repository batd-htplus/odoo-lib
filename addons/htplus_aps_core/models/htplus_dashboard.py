from datetime import timedelta

from odoo import api, fields, models, _


class HtplusDashboardKpi(models.Model):
    _name = 'htplus.dashboard.kpi'
    _description = 'APS Dashboard KPI'
    _table = 'htplus_dashboard_kpi'
    _check_company_auto = True

    name = fields.Char(string='Dashboard', default=lambda self: _('Production Dashboard'))
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    dashboard_type = fields.Selection([
        ('production', 'Production'),
        ('shift', 'Shift Management'),
    ], string='Dashboard Type', default='production', required=True,
        help='Which concern this dashboard reflects: APS production or shift/manning.')
    date_from = fields.Date(
        default=lambda self: fields.Date.context_today(self) - timedelta(days=7),
        help='Start of the analysed window. Defaults to a week back: opening on a '
             'single day shows nothing but zeros and reads as a broken screen.')
    date_to = fields.Date(
        default=lambda self: fields.Date.context_today(self) + timedelta(days=7))
    production_plan_id = fields.Many2one(
        'htplus.production.plan',
        string='Working Production Plan',
        help='When set, KPIs and alerts focus on this plan.',
    )

    plan_count = fields.Integer(string='Production Plans', compute='_compute_planning')
    demand_qty = fields.Float(string='Demand Qty', compute='_compute_planning')
    planned_qty = fields.Float(string='Planned Qty', compute='_compute_planning')
    material_shortage_count = fields.Integer(
        string='Material Shortages', compute='_compute_planning')
    workorder_count = fields.Integer(string='Work Orders', compute='_compute_schedule')
    scheduled_wo = fields.Integer(string='Scheduled WO', compute='_compute_schedule')
    locked_wo = fields.Integer(string='Locked WO', compute='_compute_schedule')
    conflict_count = fields.Integer(string='Schedule Conflicts', compute='_compute_schedule')
    late_wo = fields.Integer(string='Late WO', compute='_compute_schedule')
    machine_down = fields.Integer(string='Machines Down', compute='_compute_machine')

    alert_summary = fields.Text(string='Alerts', compute='_compute_alert_summary')

    def _plan_workorder_domain(self):
        self.ensure_one()
        domain = [('state', '!=', 'cancel')]
        if self.production_plan_id:
            domain.append(('production_id.htplus_plan_id', '=', self.production_plan_id.id))
        return domain

    @api.depends('date_from', 'date_to', 'production_plan_id')
    def _compute_planning(self):
        """Aggregate planning KPIs within the selected window."""
        for rec in self:
            plan_domain = [('state', 'in', ['approved', 'locked'])]
            line_domain = [
                ('date_deadline', '>=', rec.date_from),
                ('date_deadline', '<=', rec.date_to),
            ]
            demand_domain = [
                ('date', '>=', rec.date_from),
                ('date', '<=', rec.date_to),
            ]
            shortage_domain = [('material_ok', '=', False), ('state', '!=', 'draft')]
            if rec.production_plan_id:
                plan_domain = [('id', '=', rec.production_plan_id.id)]
                line_domain.append(('plan_id', '=', rec.production_plan_id.id))
                shortage_domain.append(('plan_id', '=', rec.production_plan_id.id))
                if rec.production_plan_id.demand_plan_id:
                    demand_domain.append(
                        ('plan_id', '=', rec.production_plan_id.demand_plan_id.id))
            rec.plan_count = self.env['htplus.production.plan'].search_count(plan_domain)
            rec.demand_qty = self._sum_qty('htplus.demand.plan.line', demand_domain)
            rec.planned_qty = self._sum_qty('htplus.production.plan.line', line_domain)
            rec.material_shortage_count = self.env['htplus.production.plan.line'].search_count(
                shortage_domain)

    @api.depends('date_from', 'date_to', 'production_plan_id')
    def _compute_schedule(self):
        """Aggregate scheduling KPIs (scheduled, locked, conflicts, late WOs)."""
        now = fields.Datetime.now()
        Workorder = self.env['mrp.workorder']
        for rec in self:
            base = rec._plan_workorder_domain()
            rows = Workorder.read_group(
                base, ['id:count'], ['schedule_state'], lazy=False)
            rec.workorder_count = sum(row['id'] for row in rows)
            rec.scheduled_wo = sum(
                row['id'] for row in rows
                if row['schedule_state'] in ('scheduled', 'confirmed', 'locked'))
            rec.locked_wo = Workorder.search_count(base + [('locked', '=', True)])
            rec.conflict_count = Workorder.search_count(base + [('schedule_conflict', '=', True)])
            rec.late_wo = Workorder.search_count(base + [
                ('date_finished', '!=', False),
                ('date_finished', '<', now),
                ('state', 'not in', ('done', 'cancel')),
            ])

    def _sum_qty(self, model, domain):
        """Sum the qty field of the given model over a domain without loading records."""
        lines = self.env[model].read_group(domain, ['qty:sum'], [])
        if not lines:
            return 0.0
        return lines[0].get('qty') or 0.0

    @api.depends()
    def _compute_machine(self):
        """Count machines currently in 'down' status."""
        for rec in self:
            rec.machine_down = self.env['htplus.machine'].search_count([('status', '=', 'down')])

    def _htplus_alert_lines(self):
        """Return the alert lines shown on the dashboard.

        HOOK - bridge modules append the alerts belonging to their capability
        by extending this rather than by editing the summary compute, so the
        dashboard never references a field that may not be installed.
        """
        self.ensure_one()
        lines = []
        if self.production_plan_id:
            lines.append(_('Working plan: %s (%s)') % (
                self.production_plan_id.name, self.production_plan_id.state))
        if self.conflict_count:
            lines.append(_('%s schedule conflict(s)') % self.conflict_count)
        if self.late_wo:
            lines.append(_('%s late work order(s)') % self.late_wo)
        if self.material_shortage_count:
            lines.append(_('%s material shortage line(s)') % self.material_shortage_count)
        if self.machine_down:
            lines.append(_('%s machine(s) down') % self.machine_down)
        return lines

    @api.depends(
        'conflict_count', 'late_wo', 'material_shortage_count', 'machine_down',
        'production_plan_id',
    )
    def _compute_alert_summary(self):
        """Render the alert lines collected from this module and any bridges."""
        for rec in self:
            lines = rec._htplus_alert_lines()
            rec.alert_summary = '\n'.join(lines) if lines else _('No alerts')

    def action_refresh(self):
        """Invalidate caches so the dashboard recomputes its KPIs."""
        self.invalidate_recordset()
        return True

    @api.model
    def action_open_dashboard(self):
        """Open the production dashboard record for the current company (create it on first visit)."""
        dash = self.search(
            [('company_id', '=', self.env.company.id),
             ('dashboard_type', '=', 'production')], order='id', limit=1)
        if not dash:
            dash = self.create({'name': _('Production Dashboard')})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dashboard'),
            'res_model': 'htplus.dashboard.kpi',
            'res_id': dash.id,
            'view_mode': 'form',
            'view_id': self.env.ref('htplus_aps_core.view_htplus_dashboard_kpi_form').id,
            'target': 'inline',
        }

    @api.model
    def _dashboard_record(self, date_from=None, date_to=None, production_plan_id=False):
        """Build an in-memory dashboard record for the given filters."""
        today = fields.Date.context_today(self)
        vals = {
            'date_from': fields.Date.to_date(date_from) if date_from else today,
            'date_to': fields.Date.to_date(date_to) if date_to else today,
            'production_plan_id': int(production_plan_id) if production_plan_id else False,
        }
        return self.new(vals)

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, production_plan_id=False):
        """Return KPI tiles, alerts and chart payloads for the OWL dashboard."""
        rec = self._dashboard_record(date_from, date_to, production_plan_id)
        plans = self.env['htplus.production.plan'].search_read(
            [], ['id', 'name', 'state'], limit=40, order='id desc',
        )
        return {
            'filters': {
                'date_from': fields.Date.to_string(rec.date_from),
                'date_to': fields.Date.to_string(rec.date_to),
                'production_plan_id': rec.production_plan_id.id or False,
                'production_plan_name': rec.production_plan_id.display_name or '',
                'plans': plans,
            },
            'alerts': [line for line in (rec.alert_summary or '').split('\n') if line],
            'kpis': rec._dashboard_kpi_cards(),
            'charts': rec._dashboard_charts(),
            'shortcuts': rec._dashboard_shortcuts(),
        }

    def _dashboard_kpi_cards(self):
        self.ensure_one()
        return [
            {'key': 'demand_qty', 'label': _('Demand Qty'), 'value': self.demand_qty, 'tone': 'info'},
            {'key': 'planned_qty', 'label': _('Planned Qty'), 'value': self.planned_qty, 'tone': 'info'},
            {'key': 'workorder_count', 'label': _('Work Orders'), 'value': self.workorder_count, 'tone': 'neutral'},
            {'key': 'scheduled_wo', 'label': _('Scheduled'), 'value': self.scheduled_wo, 'tone': 'ok'},
            {'key': 'conflict_count', 'label': _('Conflicts'), 'value': self.conflict_count, 'tone': 'danger'},
            {'key': 'late_wo', 'label': _('Late WO'), 'value': self.late_wo, 'tone': 'warn'},
            {'key': 'material_shortage_count', 'label': _('Material Short'), 'value': self.material_shortage_count, 'tone': 'danger'},
            {'key': 'machine_down', 'label': _('Machines Down'), 'value': self.machine_down, 'tone': 'danger'},
            {'key': 'shortage_shifts', 'label': _('Shift Shortage'), 'value': self.shortage_shifts, 'tone': 'warn'},
            {'key': 'assignment_rate', 'label': _('Assignment %'), 'value': round(self.assignment_rate, 1), 'tone': 'ok'},
            {'key': 'completion_rate', 'label': _('Completion %'), 'value': round(self.completion_rate, 1), 'tone': 'ok'},
            {'key': 'total_ot_minutes', 'label': _('OT (min)'), 'value': self.total_ot_minutes, 'tone': 'neutral'},
        ]

    def _dashboard_charts(self):
        self.ensure_one()
        return [
            self._chart_demand_vs_plan(),
            self._chart_wo_status(),
            self._chart_risk_signals(),
            self._chart_shift_health(),
        ]

    def _chart_demand_vs_plan(self):
        self.ensure_one()
        demand_domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        plan_domain = [
            ('date_deadline', '>=', self.date_from),
            ('date_deadline', '<=', self.date_to),
        ]
        if self.production_plan_id:
            plan_domain.append(('plan_id', '=', self.production_plan_id.id))
            if self.production_plan_id.demand_plan_id:
                demand_domain.append(('plan_id', '=', self.production_plan_id.demand_plan_id.id))
        demand_rows = self.env['htplus.demand.plan.line'].read_group(
            demand_domain, ['qty:sum'], ['date:day'],
        )
        plan_rows = self.env['htplus.production.plan.line'].read_group(
            plan_domain, ['qty:sum'], ['date_deadline:day'],
        )
        by_day = {}
        for row in demand_rows:
            label = (row.get('date:day') or row.get('date') or '')[:10]
            if not label:
                continue
            by_day.setdefault(label, {'demand': 0.0, 'planned': 0.0})
            by_day[label]['demand'] = row.get('qty') or 0.0
        for row in plan_rows:
            label = (row.get('date_deadline:day') or row.get('date_deadline') or '')[:10]
            if not label:
                continue
            by_day.setdefault(label, {'demand': 0.0, 'planned': 0.0})
            by_day[label]['planned'] = row.get('qty') or 0.0
        labels = sorted(by_day)
        return {
            'id': 'demand_vs_plan',
            'title': _('Demand vs Planned'),
            'type': 'bar',
            'labels': labels,
            'datasets': [
                {
                    'label': _('Demand'),
                    'data': [by_day[d]['demand'] for d in labels],
                    'backgroundColor': '#0d9488',
                },
                {
                    'label': _('Planned'),
                    'data': [by_day[d]['planned'] for d in labels],
                    'backgroundColor': '#2563eb',
                },
            ],
        }

    def _chart_wo_status(self):
        self.ensure_one()
        Workorder = self.env['mrp.workorder']
        base = self._plan_workorder_domain()
        buckets = [
            (_('Unscheduled'), [('schedule_state', '=', 'unscheduled')], '#94a3b8'),
            (_('Scheduled'), [('schedule_state', '=', 'scheduled')], '#2563eb'),
            (_('Confirmed'), [('schedule_state', '=', 'confirmed')], '#0d9488'),
            (_('Locked'), [('schedule_state', '=', 'locked')], '#475569'),
            (_('Done'), [('state', '=', 'done')], '#16a34a'),
        ]
        labels, data, colors = [], [], []
        for label, domain, color in buckets:
            count = Workorder.search_count(base + domain)
            if count:
                labels.append(label)
                data.append(count)
                colors.append(color)
        return {
            'id': 'wo_status',
            'title': _('Work Order Status'),
            'type': 'doughnut',
            'labels': labels or [_('No data')],
            'datasets': [{
                'data': data or [1],
                'backgroundColor': colors or ['#e2e8f0'],
            }],
        }

    def _chart_risk_signals(self):
        self.ensure_one()
        labels = [
            _('Conflicts'), _('Late WO'), _('Material'),
            _('Shift short'), _('Assignment'), _('Machine down'),
        ]
        data = [
            self.conflict_count, self.late_wo, self.material_shortage_count,
            self.shortage_shifts, self.assignment_conflict_count, self.machine_down,
        ]
        return {
            'id': 'risk_signals',
            'title': _('Risk Signals'),
            'type': 'bar',
            'horizontal': True,
            'labels': labels,
            'datasets': [{
                'label': _('Count'),
                'data': data,
                'backgroundColor': [
                    '#dc2626', '#f59e0b', '#dc2626', '#f59e0b', '#f59e0b', '#dc2626',
                ],
            }],
        }

    def _chart_shift_health(self):
        self.ensure_one()
        return {
            'id': 'shift_health',
            'title': _('Shift Progress'),
            'type': 'bar',
            'labels': [_('Total'), _('Confirmed'), _('Completed'), _('Short')],
            'datasets': [{
                'label': _('Shifts'),
                'data': [
                    self.total_shifts, self.confirmed_shifts,
                    self.completed_shifts, self.shortage_shifts,
                ],
                'backgroundColor': ['#64748b', '#2563eb', '#16a34a', '#f59e0b'],
            }],
        }

    def _dashboard_shortcuts(self):
        self.ensure_one()
        return [
            {'key': 'working_plan', 'label': _('Working Plan')},
            {'key': 'gantt', 'label': _('Gantt')},
            {'key': 'schedule', 'label': _('Schedule Runs')},
            {'key': 'workorders', 'label': _('Work Orders')},
            {'key': 'conflicts', 'label': _('Conflicts')},
            {'key': 'material', 'label': _('Material Shortages')},
            {'key': 'shifts', 'label': _('Shifts')},
        ]

    @api.model
    def get_dashboard_action(self, key, date_from=None, date_to=None, production_plan_id=False):
        """Resolve a dashboard shortcut into an ir.actions payload."""
        rec = self._dashboard_record(date_from, date_to, production_plan_id)
        actions = {
            'working_plan': rec.action_open_working_plan,
            'gantt': rec.action_open_gantt,
            'schedule': rec.action_open_schedule,
            'workorders': rec.action_open_workorders,
            'conflicts': rec.action_open_conflicts,
            'material': rec.action_open_material_shortages,
            'shifts': rec.action_open_shifts,
        }
        method = actions.get(key)
        if not method:
            return False
        return method()

    def action_open_working_plan(self):
        self.ensure_one()
        if not self.production_plan_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Production Plans'),
                'res_model': 'htplus.production.plan',
                'view_mode': 'list,form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Plan'),
            'res_model': 'htplus.production.plan',
            'res_id': self.production_plan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_schedule(self):
        """Open the schedule runs list (filtered by working plan when set)."""
        domain = []
        context = {}
        if self.production_plan_id:
            domain = [('production_plan_id', '=', self.production_plan_id.id)]
            context['default_production_plan_id'] = self.production_plan_id.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.schedule.run',
            'view_mode': 'list,form',
            'name': _('Schedule Runs'),
            'domain': domain,
            'context': context,
        }

    def action_open_workorders(self):
        """Open work orders (filtered by working plan when set)."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'list,form',
            'name': _('Work Orders'),
            'domain': self._plan_workorder_domain(),
        }

    def action_open_conflicts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'list,form',
            'name': _('Schedule Conflicts'),
            'domain': self._plan_workorder_domain() + [('schedule_conflict', '=', True)],
        }

    def action_open_material_shortages(self):
        self.ensure_one()
        domain = [('material_ok', '=', False)]
        if self.production_plan_id:
            domain.append(('plan_id', '=', self.production_plan_id.id))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.plan.line',
            'view_mode': 'list,form',
            'name': _('Material Shortages'),
            'domain': domain,
        }

    def action_open_gantt(self):
        self.ensure_one()
        ctx = {}
        if self.production_plan_id:
            ctx['htplus_production_plan_id'] = self.production_plan_id.id
        return {
            'type': 'ir.actions.client',
            'tag': 'htplus_aps_core.gantt',
            'name': _('Gantt'),
            'context': ctx,
        }
