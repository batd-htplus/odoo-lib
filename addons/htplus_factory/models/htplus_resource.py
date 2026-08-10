from odoo import fields, models


class ResourceCalendarAttendance(models.Model):
    _inherit = 'resource.calendar.attendance'

    htplus_shift_template_id = fields.Many2one(
        'htplus.shift.template',
        string='HTPlus Shift Template',
        ondelete='cascade',
        index=True,
        help='Marks attendance lines generated from an HTPlus shift pattern.',
    )


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    htplus_factory_holiday_id = fields.Many2one(
        'htplus.factory.holiday',
        string='HTPlus Factory Holiday',
        ondelete='cascade',
        index=True,
    )
