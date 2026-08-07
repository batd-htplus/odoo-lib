from odoo import api, fields, models


class HtplusDowntimeReason(models.Model):
    _name = 'htplus.downtime.reason'
    _description = 'Downtime Reason'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    category = fields.Selection([
        ('breakdown', 'Breakdown'),
        ('setup', 'Setup'),
        ('wait_material', 'Waiting Material'),
        ('wait_machine', 'Waiting Machine'),
        ('wait_manpower', 'Waiting Manpower'),
        ('power', 'Power Outage'),
        ('quality', 'Quality'),
        ('other', 'Other'),
    ], default='other')
    active = fields.Boolean(default=True)


class HtplusDowntime(models.Model):
    _name = 'htplus.downtime'
    _description = 'Downtime'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    machine_id = fields.Many2one('htplus.machine', string='Machine')
    reason_id = fields.Many2one('htplus.downtime.reason', required=True, string='Reason')
    type = fields.Selection([
        ('planned', 'Planned'),
        ('unplanned', 'Unplanned'),
    ], default='unplanned')
    date_start = fields.Datetime(required=True, string='Start')
    date_end = fields.Datetime(string='End')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    cost = fields.Float()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_end and rec.date_start:
                delta = rec.date_end - rec.date_start
                rec.duration_minutes = delta.total_seconds() / 60.0
            else:
                rec.duration_minutes = 0.0

    duration_minutes = fields.Float(compute='_compute_duration', string='Duration (minutes)')
