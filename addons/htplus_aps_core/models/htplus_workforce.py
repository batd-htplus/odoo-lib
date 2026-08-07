from odoo import fields, models
from odoo.exceptions import ValidationError


class HtplusWorkforceAssignment(models.Model):
    _name = 'htplus.workforce.assignment'
    _description = 'Workforce Assignment'

    name = fields.Char(required=True)
    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    employee_id = fields.Many2one('hr.employee', required=True, string='Employee')
    shift_template_id = fields.Many2one('htplus.shift.template', string='Shift Template')
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

    def action_validate(self):
        for assignment in self:
            skills = self.env['htplus.employee.skill'].search([
                ('employee_id', '=', assignment.employee_id.id),
            ])
            assignment.skill_ok = bool(skills)
            conflicts = self.search([
                ('employee_id', '=', assignment.employee_id.id),
                ('id', '!=', assignment.id),
                ('date_start', '>=', assignment.date_start),
                ('date_start', '<', assignment.date_end),
                ('state', '=', 'confirmed'),
            ])
            assignment.conflict = bool(conflicts)
            assignment.ot_ok = not assignment.conflict

    def action_confirm(self):
        self.action_validate()
        for assignment in self:
            if assignment.conflict:
                raise ValidationError('Shift conflict detected for %s.' % assignment.employee_id.name)
        self.state = 'confirmed'

    def action_cancel(self):
        self.state = 'cancelled'
