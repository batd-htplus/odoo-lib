from odoo import api, fields, models, _


class HtplusDashboardKpi(models.Model):
    _name = 'htplus.dashboard.kpi'
    _description = 'APS Dashboard KPI'
    _table = 'htplus_dashboard_kpi'

    name = fields.Char(string='Dashboard', default=lambda self: _('Production Dashboard'))
    date_from = fields.Date(default=fields.Date.context_today)
    date_to = fields.Date(default=fields.Date.context_today)

    plan_count = fields.Integer(string='Production Plans', compute='_compute_planning')
    demand_qty = fields.Float(string='Demand Qty', compute='_compute_planning')
    planned_qty = fields.Float(string='Planned Qty', compute='_compute_planning')
    workorder_count = fields.Integer(string='Work Orders', compute='_compute_schedule')
    scheduled_wo = fields.Integer(string='Scheduled WO', compute='_compute_schedule')
    locked_wo = fields.Integer(string='Locked WO', compute='_compute_schedule')
    conflict_count = fields.Integer(string='Schedule Conflicts', compute='_compute_schedule')
    late_wo = fields.Integer(string='Late WO', compute='_compute_schedule')
    machine_down = fields.Integer(string='Machines Down', compute='_compute_machine')

    total_shifts = fields.Integer(string='Total Shifts', compute='_compute_shift')
    confirmed_shifts = fields.Integer(string='Confirmed Shifts', compute='_compute_shift')
    completed_shifts = fields.Integer(string='Completed Shifts', compute='_compute_shift')
    assignment_rate = fields.Float(string='Assignment Rate (%)', compute='_compute_shift')
    completion_rate = fields.Float(string='Completion Rate (%)', compute='_compute_shift')
    shortage_shifts = fields.Integer(string='Shifts Short Manpower', compute='_compute_shift')
    total_ot_minutes = fields.Float(string='Total OT (min)', compute='_compute_shift')

    @api.depends('date_from', 'date_to')
    def _compute_planning(self):
        """Aggregate planning KPIs within the selected window."""
        for rec in self:
            rec.plan_count = self.env['htplus.production.plan'].search_count([
                ('state', 'in', ['approved', 'locked']),
            ])
            rec.demand_qty = self._sum_qty('htplus.demand.plan.line',
                                           [('date', '>=', rec.date_from), ('date', '<=', rec.date_to)])
            rec.planned_qty = self._sum_qty('htplus.production.plan.line',
                                            [('date_deadline', '>=', rec.date_from), ('date_deadline', '<=', rec.date_to)])

    @api.depends('date_from', 'date_to')
    def _compute_schedule(self):
        """Aggregate scheduling KPIs (scheduled, locked, conflicts, late WOs)."""
        now = fields.Datetime.now()
        Workorder = self.env['mrp.workorder']
        stats = {
            'workorder_count': Workorder.search_count([]),
            'scheduled_wo': Workorder.search_count([
                ('schedule_state', 'in', ('scheduled', 'confirmed', 'locked')),
            ]),
            'locked_wo': Workorder.search_count([('locked', '=', True)]),
            'conflict_count': Workorder.search_count([('schedule_conflict', '=', True)]),
            'late_wo': Workorder.search_count([
                ('date_finished', '!=', False),
                ('date_finished', '<', now),
                ('state', 'not in', ('done', 'cancel')),
            ]),
        }
        for rec in self:
            rec.workorder_count = stats['workorder_count']
            rec.scheduled_wo = stats['scheduled_wo']
            rec.locked_wo = stats['locked_wo']
            rec.conflict_count = stats['conflict_count']
            rec.late_wo = stats['late_wo']

    def _sum_qty(self, model, domain):
        """Sum the qty field of the given model over a domain without loading records."""
        lines = self.env[model].read_group(domain, ['qty'], [])
        if not lines:
            return 0.0
        return lines[0]['qty'] or 0.0

    @api.depends('date_from', 'date_to')
    def _compute_shift(self):
        """Aggregate shift KPIs (manpower, completion and overtime)."""
        for rec in self:
            domain = [('date', '>=', rec.date_from), ('date', '<=', rec.date_to)]
            Shift = self.env['htplus.production.shift']
            Completion = self.env['htplus.shift.completion']
            rec.total_shifts = Shift.search_count(domain)
            rec.confirmed_shifts = Shift.search_count(domain + [('state', '=', 'confirmed')])
            rec.completed_shifts = Shift.search_count(domain + [('state', '=', 'completed')])
            rec.shortage_shifts = Shift.search_count(domain + [
                ('state', '=', 'confirmed'),
                ('manpower_assigned', '<', 'manpower_required'),
            ])
            totals = Shift.read_group(domain, ['manpower_assigned', 'manpower_required'], [])
            if totals:
                assigned = totals[0]['manpower_assigned'] or 0.0
                required = totals[0]['manpower_required'] or 0.0
            else:
                assigned = required = 0.0
            rec.assignment_rate = assigned / required * 100 if required else 0.0
            done = Completion.search_count(domain + [('qty_done', '>', 0)])
            total = Completion.search_count(domain)
            rec.completion_rate = done / total * 100 if total else 0.0
            overtime = Completion.read_group(domain, ['overtime_minutes'], [])
            rec.total_ot_minutes = overtime[0]['overtime_minutes'] or 0.0 if overtime else 0.0

    @api.depends()
    def _compute_machine(self):
        """Count machines currently in 'down' status."""
        for rec in self:
            rec.machine_down = self.env['htplus.machine'].search_count([('status', '=', 'down')])

    def action_refresh(self):
        """Invalidate caches so the dashboard recomputes its KPIs."""
        self.invalidate_recordset()
        return True

    def action_open_schedule(self):
        """Open the schedule runs list."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.schedule.run',
            'view_mode': 'tree,form',
            'name': _('Schedule Runs'),
        }

    def action_open_workorders(self):
        """Open the work orders list."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'tree,form',
            'name': _('Work Orders'),
        }

    def action_open_shifts(self):
        """Open the shifts within the selected window."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.shift',
            'view_mode': 'list,form',
            'name': _('Shifts'),
            'domain': [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
        }
