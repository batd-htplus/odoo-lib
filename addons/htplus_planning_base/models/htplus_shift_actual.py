from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HtplusShiftActual(models.Model):
    _name = 'htplus.shift.actual'
    _description = 'Shift Actual'
    _order = 'date desc, shift_id'
    _rec_name = 'display_name'

    name = fields.Char(required=True, default=lambda self: _('New'))
    shift_id = fields.Many2one('htplus.production.shift', string='Shift')
    date = fields.Date(required=True, string='Work Date')
    factory_id = fields.Many2one('htplus.factory', string='Factory')
    plant_id = fields.Many2one('htplus.plant', string='Plant')
    line_id = fields.Many2one('htplus.line', string='Line')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    leader_id = fields.Many2one('hr.employee', string='Leader')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status')

    line_ids = fields.One2many('htplus.shift.actual.line', 'actual_id',
                               string='Actual Lines')

    qty_target = fields.Float(compute='_compute_totals', string='Target Qty', store=True)
    qty_done = fields.Float(compute='_compute_totals', string='Done Qty', store=True)
    qty_good = fields.Float(compute='_compute_totals', string='Good Qty', store=True)
    qty_ng = fields.Float(compute='_compute_totals', string='NG Qty', store=True)
    downtime_minutes = fields.Float(compute='_compute_totals', string='Downtime (min)', store=True)
    overtime_minutes = fields.Float(compute='_compute_totals', string='Overtime (min)', store=True)
    manpower_used = fields.Integer(compute='_compute_totals', string='Manpower Used', store=True)
    achievement_rate = fields.Float(compute='_compute_totals', string='Achievement Rate (%)', store=True)
    yield_rate = fields.Float(compute='_compute_totals', string='Yield Rate (%)', store=True)
    remarks = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('line_ids', 'line_ids.qty_target', 'line_ids.qty_done',
                 'line_ids.qty_good', 'line_ids.qty_ng', 'line_ids.downtime_minutes',
                 'line_ids.overtime_minutes', 'line_ids.employee_id')
    def _compute_totals(self):
        """Aggregate the per-work-order actual lines into shift totals."""
        for rec in self:
            rec.qty_target = sum(rec.line_ids.mapped('qty_target'))
            rec.qty_done = sum(rec.line_ids.mapped('qty_done'))
            rec.qty_good = sum(rec.line_ids.mapped('qty_good'))
            rec.qty_ng = sum(rec.line_ids.mapped('qty_ng'))
            rec.downtime_minutes = sum(rec.line_ids.mapped('downtime_minutes'))
            rec.overtime_minutes = sum(rec.line_ids.mapped('overtime_minutes'))
            rec.manpower_used = len(rec.line_ids.mapped('employee_id').filtered(lambda e: e))
            rec.achievement_rate = (rec.qty_done / rec.qty_target * 100) if rec.qty_target else 0.0
            rec.yield_rate = (rec.qty_good / rec.qty_done * 100) if rec.qty_done else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        """Number new actuals and inherit shift attributes."""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.shift.actual') or _('New')
            if vals.get('shift_id'):
                shift = self.env['htplus.production.shift'].browse(vals['shift_id'])
                vals.setdefault('date', shift.date)
                vals.setdefault('factory_id', shift.factory_id.id)
                vals.setdefault('plant_id', shift.plant_id.id)
                vals.setdefault('line_id', shift.line_id.id)
                vals.setdefault('workcenter_id', shift.workcenter_id.id)
                vals.setdefault('leader_id', shift.leader_id.id)
        return super().create(vals_list)

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        """Carry shift date, line and leader onto the actual record."""
        if self.shift_id:
            self.date = self.shift_id.date
            self.factory_id = self.shift_id.factory_id
            self.plant_id = self.shift_id.plant_id
            self.line_id = self.shift_id.line_id
            self.workcenter_id = self.shift_id.workcenter_id
            self.leader_id = self.shift_id.leader_id

    def action_generate_from_shift(self):
        """Create actual lines from the confirmed shift assignments."""
        self.ensure_one()
        if not self.shift_id:
            return
        assignments = self.shift_id.assignment_ids.filtered(lambda a: a.state == 'confirmed')
        existing = self.line_ids.mapped('assignment_id')
        vals_list = []
        for assignment in assignments:
            if assignment in existing:
                continue
            vals_list.append({
                'assignment_id': assignment.id,
                'workorder_id': assignment.workorder_id.id,
                'employee_id': assignment.employee_id.id,
                'qty_target': assignment.qty,
                'date': self.date,
            })
        if vals_list:
            self.line_ids = [(0, 0, vals) for vals in vals_list]
        return True

    def action_confirm(self):
        """Move the actual to In Progress once it has lines."""
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Add at least one actual line before starting.'))
        self.state = 'in_progress'

    def action_done(self):
        """Mark the shift actual as done."""
        self.state = 'done'

    def action_cancel(self):
        """Cancel the shift actual."""
        self.state = 'cancelled'

    def action_open_shift(self):
        """Open the linked production shift."""
        self.ensure_one()
        if not self.shift_id:
            return
        return {
            'name': _('Shift'),
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.shift',
            'res_id': self.shift_id.id,
            'view_mode': 'form',
        }


class HtplusShiftActualLine(models.Model):
    _name = 'htplus.shift.actual.line'
    _description = 'Shift Actual Line'
    _order = 'actual_id, workorder_id'

    actual_id = fields.Many2one('htplus.shift.actual', required=True, ondelete='cascade',
                                string='Shift Actual')
    date = fields.Date(related='actual_id.date', string='Work Date', store=True)
    shift_id = fields.Many2one(related='actual_id.shift_id', string='Shift', store=True)
    assignment_id = fields.Many2one('htplus.workforce.assignment', string='Assignment')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    qty_target = fields.Float(string='Target Qty')
    qty_done = fields.Float(string='Done Qty')
    qty_good = fields.Float(string='Good Qty')
    qty_ng = fields.Float(string='NG Qty')
    downtime_minutes = fields.Float(string='Downtime (min)')
    overtime_minutes = fields.Float(string='Overtime (min)')

    @api.depends('qty_done', 'qty_target')
    def _compute_achievement_rate(self):
        """Share of the target quantity that was actually produced."""
        for rec in self:
            rec.achievement_rate = (rec.qty_done / rec.qty_target * 100) if rec.qty_target else 0.0

    achievement_rate = fields.Float(compute='_compute_achievement_rate',
                                    string='Achievement Rate (%)')

    @api.depends('qty_good', 'qty_done')
    def _compute_yield_rate(self):
        """Share of the produced quantity that is good."""
        for rec in self:
            rec.yield_rate = (rec.qty_good / rec.qty_done * 100) if rec.qty_done else 0.0

    yield_rate = fields.Float(compute='_compute_yield_rate', string='Yield Rate (%)')

    @api.onchange('assignment_id')
    def _onchange_assignment_id(self):
        """Carry the work order, employee and target qty from the assignment."""
        if self.assignment_id:
            self.workorder_id = self.assignment_id.workorder_id
            self.employee_id = self.assignment_id.employee_id
            if not self.qty_target:
                self.qty_target = self.assignment_id.qty
