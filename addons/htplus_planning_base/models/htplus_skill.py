from odoo import fields, models


class HtplusSkill(models.Model):
    _name = 'htplus.skill'
    _description = 'Skill'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)


class HtplusEmployeeSkill(models.Model):
    _name = 'htplus.employee.skill'
    _description = 'Employee Skill'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    skill_id = fields.Many2one('htplus.skill', required=True, ondelete='cascade')
    level = fields.Selection([
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ], default='basic')
    certified = fields.Boolean()
    last_assessed = fields.Date(string='Last Assessed')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('employee_skill_uniq', 'unique(employee_id, skill_id)',
         'This skill is already assigned to the employee.'),
    ]
