from odoo import fields, models


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    htplus_factory_holiday_id = fields.Many2one(
        'htplus.factory.holiday',
        string='HTPlus Factory Holiday',
        ondelete='cascade',
        index=True,
    )
