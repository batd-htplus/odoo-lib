from odoo import api, fields, models


class HtplusMachine(models.Model):
    _name = 'htplus.machine'
    _inherit = ['htplus.factory.scope.mixin']
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

    @api.depends('workcenter_id', 'workcenter_id.factory_id',
                 'line_id', 'line_id.factory_id',
                 'plant_id', 'plant_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a machine by whichever link it actually carries.

        A machine may be recorded against a work center, a line or just a
        plant. Deriving from one of them only would leave factory_id empty on
        the others - and an empty scope means the machine is invisible to
        everyone, which is a silent way to lose data.
        """
        for machine in self:
            machine.factory_id = (
                machine.workcenter_id.factory_id
                or machine.line_id.factory_id
                or machine.plant_id.factory_id
                or False
            )

