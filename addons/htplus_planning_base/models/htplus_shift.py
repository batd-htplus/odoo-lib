from odoo import api, fields, models


class HtplusShiftTemplate(models.Model):
    _name = 'htplus.shift.template'
    _description = 'Shift Template'
    _order = 'start_time'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    start_time = fields.Float(string='Start Time', help='Hours since midnight', required=True)
    end_time = fields.Float(string='End Time', help='Hours since midnight', required=True)
    is_overtime = fields.Boolean(string='Overtime Shift')
    active = fields.Boolean(default=True)

    @api.depends('start_time', 'end_time')
    def _compute_total_hours(self):
        for rec in self:
            total = rec.end_time - rec.start_time
            if total < 0:
                total += 24.0
            rec.total_hours = total

    total_hours = fields.Float(compute='_compute_total_hours', string='Total Hours')


class HtplusShiftPattern(models.Model):
    _name = 'htplus.shift.pattern'
    _description = 'Shift Pattern'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    line_ids = fields.One2many('htplus.shift.pattern.line', 'pattern_id', string='Lines')
    active = fields.Boolean(default=True)


class HtplusShiftPatternLine(models.Model):
    _name = 'htplus.shift.pattern.line'
    _description = 'Shift Pattern Line'

    pattern_id = fields.Many2one('htplus.shift.pattern', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    weekday = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], required=True)
    template_id = fields.Many2one('htplus.shift.template', string='Shift Template', required=True)

    _sql_constraints = [
        ('pattern_weekday_uniq', 'unique(pattern_id, weekday, template_id)',
         'A shift template is already defined for this weekday.'),
    ]


class HtplusHolidayCalendar(models.Model):
    _name = 'htplus.holiday.calendar'
    _description = 'Holiday Calendar'

    name = fields.Char(required=True)
    year = fields.Integer(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    line_ids = fields.One2many('htplus.holiday.line', 'calendar_id', string='Holidays')
    active = fields.Boolean(default=True)


class HtplusHolidayLine(models.Model):
    _name = 'htplus.holiday.line'
    _description = 'Holiday Line'

    calendar_id = fields.Many2one('htplus.holiday.calendar', required=True, ondelete='cascade')
    date = fields.Date(required=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
