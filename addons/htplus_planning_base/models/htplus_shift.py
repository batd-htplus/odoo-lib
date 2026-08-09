from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class HtplusShiftTemplate(models.Model):
    _name = 'htplus.shift.template'
    _description = 'Shift Template'
    _order = 'factory_id, code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color', help='Used by the calendar and kanban color pickers.')

    shift_type = fields.Selection([
        ('day', 'Day'),
        ('evening', 'Evening'),
        ('night', 'Night'),
        ('overtime', 'Overtime'),
    ], default='day', required=True, string='Shift Type')

    start_time = fields.Float(string='Start', required=True, default=8.0)
    end_time = fields.Float(string='End', required=True, default=17.0)
    break_minutes = fields.Float(string='Break (minutes)', default=0.0)

    _WEEKDAYS = [
        ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'),
        ('3', 'Thursday'), ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday'),
    ]
    day_of_week_start = fields.Selection(_WEEKDAYS, default='0', string='From Weekday')
    day_of_week_end = fields.Selection(_WEEKDAYS, default='4', string='To Weekday')

    default_manpower = fields.Integer(string='Default Manpower', default=1)
    factory_id = fields.Many2one('htplus.factory', string='Factory')
    plant_id = fields.Many2one('htplus.plant', string='Plant')
    line_id = fields.Many2one('htplus.line', string='Line')
    resource_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Working Hours',
        help='Target Odoo calendar for this pattern (defaults to the factory calendar).',
    )
    attendance_ids = fields.One2many(
        'resource.calendar.attendance',
        'htplus_shift_template_id',
        string='Calendar Attendances',
        readonly=True,
    )

    total_hours = fields.Float(compute='_compute_total_hours', string='Total Hours', store=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'A shift template with this code already exists.'),
    ]

    @api.depends('start_time', 'end_time', 'break_minutes')
    def _compute_total_hours(self):
        for rec in self:
            total = rec.end_time - rec.start_time
            if total <= 0:
                total += 24.0
            rec.total_hours = max(total - (rec.break_minutes or 0.0) / 60.0, 0.0)

    def _target_calendar(self):
        self.ensure_one()
        if self.resource_calendar_id:
            return self.resource_calendar_id
        if self.factory_id:
            return self.factory_id._ensure_resource_calendar()
        return False

    def _day_period_for(self, hour_from):
        return 'morning' if (hour_from or 0.0) < 12.0 else 'afternoon'

    def _attendance_vals_for_day(self, calendar, dayofweek):
        """Build attendance line vals. Overnight shifts split across midnight."""
        self.ensure_one()
        start = self.start_time or 0.0
        end = self.end_time or 0.0
        lines = []
        if end > start:
            lines.append({
                'name': self.name,
                'dayofweek': dayofweek,
                'hour_from': start,
                'hour_to': end,
                'day_period': self._day_period_for(start),
                'calendar_id': calendar.id,
                'htplus_shift_template_id': self.id,
            })
        else:
            # e.g. 22:00 -> 06:00
            lines.append({
                'name': _('%s (evening)', self.name),
                'dayofweek': dayofweek,
                'hour_from': start,
                'hour_to': 24.0,
                'day_period': 'afternoon',
                'calendar_id': calendar.id,
                'htplus_shift_template_id': self.id,
            })
            next_day = str((int(dayofweek) + 1) % 7)
            lines.append({
                'name': _('%s (morning)', self.name),
                'dayofweek': next_day,
                'hour_from': 0.0,
                'hour_to': end,
                'day_period': 'morning',
                'calendar_id': calendar.id,
                'htplus_shift_template_id': self.id,
            })
        if self.break_minutes and end > start:
            mid = (start + end) / 2.0
            break_h = (self.break_minutes or 0.0) / 60.0
            lunch_from = max(start, mid - break_h / 2.0)
            lunch_to = min(end, lunch_from + break_h)
            if lunch_to > lunch_from:
                lines.append({
                    'name': _('%s (break)', self.name),
                    'dayofweek': dayofweek,
                    'hour_from': lunch_from,
                    'hour_to': lunch_to,
                    'day_period': 'lunch',
                    'calendar_id': calendar.id,
                    'htplus_shift_template_id': self.id,
                })
        return lines

    def action_sync_to_calendar(self):
        Attendance = self.env['resource.calendar.attendance']
        for template in self:
            calendar = template._target_calendar()
            if not calendar:
                raise ValidationError(
                    _('Set a factory (or working hours) on shift pattern %s before syncing.')
                    % template.display_name
                )
            if not template.resource_calendar_id:
                template.with_context(htplus_skip_attendance_sync=True).write({
                    'resource_calendar_id': calendar.id,
                })
            template.attendance_ids.unlink()
            start_d = int(template.day_of_week_start or '0')
            end_d = int(template.day_of_week_end or '4')
            if end_d < start_d:
                days = list(range(start_d, 7)) + list(range(0, end_d + 1))
            else:
                days = list(range(start_d, end_d + 1))
            vals_list = []
            for day in days:
                vals_list.extend(template._attendance_vals_for_day(calendar, str(day)))
            if vals_list:
                Attendance.create(vals_list)
            if template.factory_id:
                template.factory_id.action_apply_calendar_to_workcenters()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates.filtered(lambda t: t.factory_id or t.resource_calendar_id).action_sync_to_calendar()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('htplus_skip_attendance_sync'):
            return res
        tracked = {
            'start_time', 'end_time', 'break_minutes', 'day_of_week_start',
            'day_of_week_end', 'factory_id', 'resource_calendar_id', 'name', 'active',
        }
        if tracked & set(vals):
            self.filtered(lambda t: t.active and (t.factory_id or t.resource_calendar_id)).action_sync_to_calendar()
        return res


class HtplusProductionShift(models.Model):
    _name = 'htplus.production.shift'
    _description = 'Production Shift'
    _order = 'date desc, template_id'
    _rec_name = 'display_name'

    name = fields.Char(required=True, default=lambda self: _('New'))
    date = fields.Date(required=True, string='Work Date')
    template_id = fields.Many2one(
        'htplus.shift.template', required=True, string='Shift')
    factory_id = fields.Many2one('htplus.factory', string='Factory')
    plant_id = fields.Many2one('htplus.plant', string='Plant')
    line_id = fields.Many2one('htplus.line', string='Line')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    leader_id = fields.Many2one('hr.employee', string='Leader')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status')
    qty_target = fields.Float(string='Planned Qty')
    qty_assigned = fields.Float(
        compute='_compute_shift_totals', string='Assigned Qty', store=True)
    manpower_required = fields.Integer(string='Required Manpower')
    manpower_assigned = fields.Integer(
        compute='_compute_shift_totals', string='Assigned Manpower', store=True)
    assignment_ids = fields.One2many(
        'htplus.workforce.assignment', 'shift_id', string='Assignments')
    completion_ids = fields.One2many(
        'htplus.shift.completion', 'shift_id', string='Actuals')
    start_time = fields.Datetime(compute='_compute_shift_time', string='Start')
    end_time = fields.Datetime(compute='_compute_shift_time', string='End')
    notes = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('shift_unique_per_line', 'unique(date, template_id, line_id)',
         'A shift already exists for this date, shift and line.'),
    ]

    @api.depends('date', 'template_id.start_time', 'template_id.end_time')
    def _compute_shift_time(self):
        for rec in self:
            if not rec.date or not rec.template_id:
                rec.start_time = rec.end_time = False
                continue
            start_hour = rec.template_id.start_time or 0.0
            end_hour = rec.template_id.end_time or 23.59
            rec.start_time = datetime.combine(
                rec.date, datetime.min.time()) + timedelta(hours=start_hour)
            end = datetime.combine(
                rec.date, datetime.min.time()) + timedelta(hours=end_hour)
            if end <= rec.start_time:
                end += timedelta(days=1)
            rec.end_time = end

    @api.depends('assignment_ids', 'assignment_ids.state', 'assignment_ids.qty')
    def _compute_shift_totals(self):
        for rec in self:
            confirmed = rec.assignment_ids.filtered(
                lambda a: a.state == 'confirmed')
            rec.manpower_assigned = len(confirmed)
            rec.qty_assigned = sum(confirmed.mapped('qty'))

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            self.factory_id = self.template_id.factory_id
            self.plant_id = self.template_id.plant_id
            self.line_id = self.template_id.line_id
            if not self.manpower_required:
                self.manpower_required = self.template_id.default_manpower

    def _check_leader_conflict(self):
        for rec in self:
            if not rec.leader_id:
                continue
            conflicts = self.search([
                ('leader_id', '=', rec.leader_id.id),
                ('id', '!=', rec.id),
                ('date', '=', rec.date),
                ('template_id', '!=', rec.template_id.id),
            ])
            if conflicts:
                raise ValidationError(
                    _('Leader %s is already assigned to another shift on this day.')
                    % rec.leader_id.name)

    def _check_machine_availability(self):
        for rec in self:
            if not rec.workcenter_id:
                continue
            conflicts = self.search([
                ('workcenter_id', '=', rec.workcenter_id.id),
                ('id', '!=', rec.id),
                ('date', '=', rec.date),
                ('state', 'in', ('draft', 'confirmed')),
            ])
            if conflicts:
                raise ValidationError(
                    _('Work center %s is already used on this date.')
                    % rec.workcenter_id.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'htplus.production.shift') or _('New')
            if not vals.get('line_id') and vals.get('template_id'):
                template = self.env['htplus.shift.template'].browse(vals['template_id'])
                vals.setdefault('factory_id', template.factory_id.id)
                vals.setdefault('plant_id', template.plant_id.id)
                vals.setdefault('line_id', template.line_id.id)
                vals.setdefault('manpower_required', template.default_manpower)
        shifts = super().create(vals_list)
        shifts._check_leader_conflict()
        shifts._check_machine_availability()
        return shifts

    def write(self, vals):
        res = super().write(vals)
        if vals.get('leader_id') or vals.get('workcenter_id'):
            self._check_leader_conflict()
            self._check_machine_availability()
        return res

    def action_confirm(self):
        for rec in self:
            if not rec.manpower_required:
                raise ValidationError(_('Required manpower must be set before confirming.'))
        self.state = 'confirmed'

    def action_complete(self):
        self.state = 'completed'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_open_assignments(self):
        return {
            'name': _('Shift Assignments'),
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.workforce.assignment',
            'view_mode': 'list,form',
            'domain': [('shift_id', '=', self.id)],
            'context': {'default_shift_id': self.id},
        }

    def action_open_actuals(self):
        return {
            'name': _('Shift Actual'),
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.shift.completion',
            'view_mode': 'list,form',
            'domain': [('shift_id', '=', self.id)],
            'context': {'default_shift_id': self.id},
        }
