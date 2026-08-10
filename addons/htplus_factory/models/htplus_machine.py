from odoo import api, fields, models


class HtplusMachine(models.Model):
    _name = 'htplus.machine'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'plant_id.factory_id'
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

    @api.depends('plant_id', 'plant_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a machine by the plant it stands in."""
        return super()._compute_htplus_factory_id()

