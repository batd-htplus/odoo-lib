from odoo import fields, models


class ResourceCalendarAttendance(models.Model):
    """Tie a working-time line back to the shift pattern that produced it.

    Lives in Workforce rather than Factory: the calendar is a Factory concern
    but shift templates are not, and Factory must not know they exist.
    """

    _inherit = 'resource.calendar.attendance'

    htplus_shift_template_id = fields.Many2one(
        'htplus.shift.template',
        string='HTPlus Shift Template',
        ondelete='cascade',
        index=True,
        help='Marks attendance lines generated from an HTPlus shift pattern.',
    )
