from datetime import datetime

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
        plans = self.env['htplus.production.plan'].search([
            ('state', 'in', ['approved', 'locked']),
        ])
        demand_lines = self.env['htplus.demand.plan.line'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        plan_lines = self.env['htplus.production.plan.line'].search([
            ('date_deadline', '>=', self.date_from),
            ('date_deadline', '<=', self.date_to),
        ])
        for rec in self:
            rec.plan_count = len(plans)
            rec.demand_qty = sum(demand_lines.mapped('qty'))
            rec.planned_qty = sum(plan_lines.mapped('qty'))

    @api.depends('date_from', 'date_to')
    def _compute_schedule(self):
        runs = self.env['htplus.schedule.run'].search([])
        workorders = self.env['mrp.workorder'].search([])
        now = datetime.now()
        for rec in self:
            rec.workorder_count = len(workorders)
            rec.scheduled_wo = len(workorders.filtered(
                lambda w: w.schedule_state in ('scheduled', 'confirmed', 'locked')))
            rec.locked_wo = len(workorders.filtered(lambda w: w.locked))
            rec.conflict_count = len(workorders.filtered(lambda w: w.schedule_conflict))
            rec.late_wo = len(workorders.filtered(
                lambda w: w.date_finished
                and w.date_finished < now
                and w.state not in ('done', 'cancel')))

    @api.depends('date_from', 'date_to')
    def _compute_shift(self):
        shifts = self.env['htplus.production.shift'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        completions = self.env['htplus.shift.completion'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        for rec in self:
            rec.total_shifts = len(shifts)
            rec.confirmed_shifts = len(shifts.filtered(lambda s: s.state == 'confirmed'))
            rec.completed_shifts = len(shifts.filtered(lambda s: s.state == 'completed'))
            rec.assignment_rate = (
                sum(s.manpower_assigned for s in shifts) /
                sum(s.manpower_required for s in shifts) * 100
            ) if sum(s.manpower_required for s in shifts) else 0.0
            rec.completion_rate = (
                len(completions.filtered(lambda c: c.qty_done > 0)) /
                len(completions) * 100
            ) if completions else 0.0
            rec.shortage_shifts = len(shifts.filtered(
                lambda s: s.state == 'confirmed'
                and s.manpower_assigned < s.manpower_required))
            rec.total_ot_minutes = sum(completions.mapped('overtime_minutes'))

    @api.depends()
    def _compute_machine(self):
        machines = self.env['htplus.machine'].search([('status', '=', 'down')])
        for rec in self:
            rec.machine_down = len(machines)

    def action_refresh(self):
        self.invalidate_recordset()
        return True

    def action_open_schedule(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.schedule.run',
            'view_mode': 'tree,form',
            'name': _('Schedule Runs'),
        }

    def action_open_workorders(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'tree,form',
            'name': _('Work Orders'),
        }

    def action_open_shifts(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.shift',
            'view_mode': 'list,form',
            'name': _('Shifts'),
            'domain': [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
        }
