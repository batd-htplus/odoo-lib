from odoo import fields, models


class HtplusMachine(models.Model):
    _name = 'htplus.machine'
    _description = 'Machine'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    model = fields.Char()
    serial_no = fields.Char()
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    line_id = fields.Many2one('htplus.line', string='Line')
    plant_id = fields.Many2one('htplus.plant', string='Plant')
    status = fields.Selection([
        ('operational', 'Operational'),
        ('standby', 'Standby'),
        ('maintenance', 'Maintenance'),
        ('down', 'Down'),
        ('retired', 'Retired'),
    ], default='operational', string='Status')
    capacity_per_hour = fields.Float(string='Capacity per Hour')
    setup_time = fields.Float(string='Setup Time (hours)')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
