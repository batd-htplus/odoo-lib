from odoo import fields, models


class HtplusFactory(models.Model):
    _name = 'htplus.factory'
    _description = 'Factory'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    plant_ids = fields.One2many('htplus.plant', 'factory_id', string='Plants')
    workcenter_ids = fields.One2many('mrp.workcenter', 'factory_id', string='Work Centers')
    active = fields.Boolean(default=True)


class HtplusPlant(models.Model):
    _name = 'htplus.plant'
    _description = 'Plant'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    factory_id = fields.Many2one('htplus.factory', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='factory_id.company_id', store=True)
    line_ids = fields.One2many('htplus.line', 'plant_id', string='Lines')
    workcenter_ids = fields.One2many('mrp.workcenter', 'plant_id', string='Work Centers')
    active = fields.Boolean(default=True)


class HtplusLine(models.Model):
    _name = 'htplus.line'
    _description = 'Production Line'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    plant_id = fields.Many2one('htplus.plant', required=True, ondelete='cascade')
    factory_id = fields.Many2one('htplus.factory', related='plant_id.factory_id', store=True)
    shift_pattern_id = fields.Many2one('htplus.shift.pattern', string='Shift Pattern')
    workcenter_ids = fields.One2many('mrp.workcenter', 'line_id', string='Work Centers')
    machine_ids = fields.One2many('htplus.machine', 'line_id', string='Machines')
    active = fields.Boolean(default=True)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    factory_id = fields.Many2one('htplus.factory')
    plant_id = fields.Many2one('htplus.plant')
    line_id = fields.Many2one('htplus.line')
    capacity_per_hour = fields.Float(string='Capacity per Hour')
    setup_time = fields.Float(string='Setup Time (hours)')
