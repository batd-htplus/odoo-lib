from odoo import api, fields, models


class HtplusShiftMember(models.Model):
    _name = 'htplus.shift.member'
    _description = 'Shift Member'
    _rec_name = 'employee_id'
    _order = 'line_id, employee_id'

    employee_id = fields.Many2one('hr.employee', required=True, string='Employee',
                                  domain="[('active', '=', True)]")
    factory_id = fields.Many2one('htplus.factory', string='Factory')
    plant_id = fields.Many2one('htplus.plant', string='Plant')
    line_id = fields.Many2one('htplus.line', string='Production Line')
    is_leader = fields.Boolean(string='Line Leader')
    start_date = fields.Date(string='Join Date', default=fields.Date.context_today)
    notes = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('employee_uniq', 'unique(employee_id)',
         'This employee is already registered as a shift member.'),
    ]

    @api.onchange('line_id')
    def _onchange_line_id(self):
        """Inherit the factory and plant from the chosen production line."""
        if self.line_id:
            self.factory_id = self.line_id.factory_id
            self.plant_id = self.line_id.plant_id
