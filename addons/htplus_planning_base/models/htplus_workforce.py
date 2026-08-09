from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtplusWorkforceAssignment(models.Model):
    _name = 'htplus.workforce.assignment'
    _description = 'Workforce Assignment'

    name = fields.Char(required=True)
    shift_id = fields.Many2one('htplus.production.shift', string='Shift')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    employee_id = fields.Many2one('hr.employee', required=True, string='Employee')
    qty = fields.Float(string='Qty')
    date_start = fields.Datetime(string='Start')
    date_end = fields.Datetime(string='End')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status')
    skill_ok = fields.Boolean(string='Skill OK')
    ot_ok = fields.Boolean(string='OT OK')
    conflict = fields.Boolean(string='Shift Conflict')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        """Number new assignments and default the timeframe from the linked shift."""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'htplus.workforce.assignment') or _('New')
            if not vals.get('date_start') and vals.get('shift_id'):
                shift = self.env['htplus.production.shift'].browse(vals['shift_id'])
                vals['date_start'] = shift.start_time
                vals['date_end'] = shift.end_time
        return super().create(vals_list)

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        """Set the assignment timeframe from the chosen shift."""
        if self.shift_id:
            self.date_start = self.shift_id.start_time
            self.date_end = self.shift_id.end_time

    def action_validate(self):
        """Check skills, shift conflicts and overtime eligibility for each assignment."""
        production_type = self.env.ref(
            'htplus_planning_base.hr_skill_type_production', raise_if_not_found=False,
        )
        for assignment in self:
            skills = self.env['hr.employee.skill'].search([
                ('employee_id', '=', assignment.employee_id.id),
            ])
            if production_type:
                assignment.skill_ok = bool(skills.filtered(
                    lambda s: s.skill_id.skill_type_id == production_type
                ))
            else:
                # No production skill taxonomy installed — do not block assignment.
                assignment.skill_ok = True
            start = assignment.date_start
            end = assignment.date_end or start
            if start and end:
                conflicts = self.search([
                    ('employee_id', '=', assignment.employee_id.id),
                    ('id', '!=', assignment.id),
                    ('date_start', '<', end),
                    ('date_end', '>', start),
                    ('state', '=', 'confirmed'),
                ])
                assignment.conflict = bool(conflicts)
            else:
                assignment.conflict = False
            assignment.ot_ok = not assignment.conflict

    def action_confirm(self):
        """Validate and confirm assignments that pass the skill and conflict checks."""
        self.action_validate()
        for assignment in self:
            if assignment.conflict:
                raise ValidationError(
                    _('Shift conflict detected for %s.')
                    % assignment.employee_id.name)
            if assignment.workorder_id and not assignment.skill_ok:
                raise ValidationError(
                    _('Employee %s has no skill for this work order.')
                    % assignment.employee_id.name)
        self.state = 'confirmed'

    def action_cancel(self):
        """Cancel the assignments."""
        self.state = 'cancelled'
