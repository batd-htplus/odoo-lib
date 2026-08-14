from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtplusWorkforceAssignment(models.Model):
    _name = 'htplus.workforce.assignment'
    _inherit = ['htplus.workflow.mixin']

    _htplus_transitions = {
        'confirm': {'from': ('draft',), 'to': 'confirmed', 'role': 'planner'},
        'cancel': {'from': ('draft', 'confirmed'), 'to': 'cancelled', 'role': 'planner'},
        'reset': {'from': ('cancelled',), 'to': 'draft', 'role': 'manager'},
    }
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


    def _htplus_skill_ok_employee_ids(self, employees):
        """Return the ids of employees qualified for production work.

        HOOK - the base Workforce module does not model skills, so it qualifies
        everybody. htplus_workforce_skills overrides this once hr_skills is
        installed.

        Args:
            employees: hr.employee recordset to evaluate.

        Returns:
            Set of qualified employee ids, or None to skip the check entirely.
        """
        return None

    def action_validate(self):
        """Check skills, shift conflicts and overtime eligibility for each assignment."""
        employees = self.mapped('employee_id')
        skill_ok_employee_ids = self._htplus_skill_ok_employee_ids(employees)
        confirmed = self.env['htplus.workforce.assignment'].search([
            ('employee_id', 'in', employees.ids),
            ('state', '=', 'confirmed'),
        ])
        for assignment in self:
            if skill_ok_employee_ids is None:
                assignment.skill_ok = True
            else:
                assignment.skill_ok = assignment.employee_id.id in skill_ok_employee_ids
            start = assignment.date_start
            end = assignment.date_end or start
            if start and end:
                assignment.conflict = any(
                    other.date_start and other.date_end
                    and other.employee_id == assignment.employee_id
                    and other.id != assignment.id
                    and other.date_start < end
                    and other.date_end > start
                    for other in confirmed
                )
            else:
                assignment.conflict = False
            assignment.ot_ok = not assignment.conflict

    def _htplus_guard_confirm(self):
        """Refuse an assignment the employee cannot actually take."""
        self.action_validate()
        if self.conflict:
            raise ValidationError(
                _('Shift conflict detected for %s.') % self.employee_id.name)
        if self.workorder_id and not self.skill_ok:
            raise ValidationError(
                _('Employee %s has no skill for this work order.') % self.employee_id.name)


class HrEmployee(models.Model):
    """Factory scoping for an employee.

    One home factory per employee. Leaves, skill checks and anything else that
    keys off "where does this person work" reference this field, so record
    rules can gate access on a single indexed column.
    """

    _inherit = 'hr.employee'

    htplus_factory_id = fields.Many2one(
        'htplus.factory',
        string='Home Factory',
        index=True,
        help='Factory this employee belongs to. Drives time-off access.',
    )
