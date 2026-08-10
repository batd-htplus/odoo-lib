from odoo import api, fields, models, _


class HtplusDashboardKpi(models.Model):
    """Shift and manning KPIs on the APS dashboard.

    Only meaningful when Workforce is installed, so the fields and their compute
    live here rather than on the dashboard itself.
    """

    _inherit = 'htplus.dashboard.kpi'

    assignment_conflict_count = fields.Integer(
        string='Assignment Conflicts', compute='_compute_shift')
    total_shifts = fields.Integer(string='Total Shifts', compute='_compute_shift')
    confirmed_shifts = fields.Integer(string='Confirmed Shifts', compute='_compute_shift')
    completed_shifts = fields.Integer(string='Completed Shifts', compute='_compute_shift')
    assignment_rate = fields.Float(string='Assignment Rate (%)', compute='_compute_shift')
    completion_rate = fields.Float(string='Completion Rate (%)', compute='_compute_shift')
    shortage_shifts = fields.Integer(string='Shifts Short Manpower', compute='_compute_shift')
    total_ot_minutes = fields.Float(string='Total OT (min)', compute='_compute_shift')

    @api.depends('date_from', 'date_to', 'production_plan_id')
    def _compute_shift(self):
        """Aggregate shift KPIs (manpower, completion and overtime)."""
        for rec in self:
            domain = [('date', '>=', rec.date_from), ('date', '<=', rec.date_to)]
            Shift = self.env['htplus.production.shift']
            Completion = self.env['htplus.shift.completion']
            Assignment = self.env['htplus.workforce.assignment']
            rec.total_shifts = Shift.search_count(domain)
            rec.confirmed_shifts = Shift.search_count(domain + [('state', '=', 'confirmed')])
            rec.completed_shifts = Shift.search_count(domain + [('state', '=', 'completed')])
            short = Shift.search(domain + [('state', '=', 'confirmed')]).filtered(
                lambda s: s.manpower_assigned < s.manpower_required
            )
            rec.shortage_shifts = len(short)
            totals = Shift.read_group(domain, ['manpower_assigned:sum', 'manpower_required:sum'], [])
            if totals:
                assigned = totals[0].get('manpower_assigned') or 0.0
                required = totals[0].get('manpower_required') or 0.0
            else:
                assigned = required = 0.0
            rec.assignment_rate = assigned / required * 100 if required else 0.0
            done = Completion.search_count(domain + [('qty_done', '>', 0)])
            total = Completion.search_count(domain)
            rec.completion_rate = done / total * 100 if total else 0.0
            overtime = Completion.read_group(domain, ['overtime_minutes:sum'], [])
            rec.total_ot_minutes = (overtime[0].get('overtime_minutes') or 0.0) if overtime else 0.0
            assign_domain = [('conflict', '=', True), ('state', '!=', 'cancelled')]
            if rec.production_plan_id:
                wo_ids = rec.production_plan_id.production_ids.mapped('workorder_ids').ids
                assign_domain.append(('workorder_id', 'in', wo_ids or [0]))
            rec.assignment_conflict_count = Assignment.search_count(assign_domain)

    def action_open_shifts(self):
        """Open the shifts within the selected window."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.shift',
            'view_mode': 'list,form',
            'name': _('Shifts'),
            'domain': [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
        }

    def _htplus_alert_lines(self):
        """Add the manning alerts, which only exist when Workforce is installed."""
        lines = super()._htplus_alert_lines()
        if self.shortage_shifts:
            lines.append(_('%s shift(s) short on manpower') % self.shortage_shifts)
        if self.assignment_conflict_count:
            lines.append(_('%s workforce assignment conflict(s)') % self.assignment_conflict_count)
        return lines

    @api.depends('shortage_shifts', 'assignment_conflict_count')
    def _compute_alert_summary(self):
        """Recompute the summary when a manning KPI moves."""
        return super()._compute_alert_summary()
