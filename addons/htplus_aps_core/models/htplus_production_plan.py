from odoo import api, fields, models, _


class HtplusProductionPlan(models.Model):
    _name = 'htplus.production.plan'
    _description = 'Production Plan'
    _inherit = ['mail.thread']
    _order = 'date_start desc'

    name = fields.Char(required=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)
    demand_plan_id = fields.Many2one('htplus.demand.plan', string='Demand Plan')
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    line_ids = fields.One2many('htplus.production.plan.line', 'plan_id', string='Lines')
    production_ids = fields.One2many('mrp.production', 'htplus_plan_id', string='Manufacturing Orders')
    schedule_run_ids = fields.One2many('htplus.schedule.run', 'production_plan_id', string='Schedule Runs')
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.production.plan') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.state = 'confirmed'

    def action_approve(self):
        self.state = 'approved'

    def action_lock(self):
        self.state = 'locked'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_create_productions(self):
        for plan in self:
            for line in plan.line_ids.filtered(lambda l: l.state == 'draft'):
                bom = line.bom_id or line.product_id.bom_ids.filtered(lambda b: b.type == 'normal')[:1]
                production = self.env['mrp.production'].create({
                    'product_id': line.product_id.id,
                    'product_qty': line.qty,
                    'product_uom_id': line.uom_id.id,
                    'bom_id': bom.id if bom else False,
                    'date_deadline': line.date_deadline,
                    'htplus_plan_id': plan.id,
                    'htplus_plan_line_id': line.id,
                })
                line.production_id = production.id
                line.state = 'confirmed'


class HtplusProductionPlanLine(models.Model):
    _name = 'htplus.production.plan.line'
    _description = 'Production Plan Line'
    _order = 'date_deadline, sequence'

    plan_id = fields.Many2one('htplus.production.plan', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    demand_line_id = fields.Many2one('htplus.demand.plan.line', string='Demand Line')
    product_id = fields.Many2one('product.product', required=True)
    qty = fields.Float(required=True)
    uom_id = fields.Many2one('uom.uom', required=True, default=lambda self: self.env['uom.uom']._get_default_uom_id())
    date_deadline = fields.Date(string='Deadline')
    bom_id = fields.Many2one('mrp.bom', string='BOM')
    routing_id = fields.Many2one('mrp.routing', string='Routing')
    priority = fields.Integer(default=0)
    workcenter_ids = fields.Many2many('mrp.workcenter', string='Work Centers')
    material_ok = fields.Boolean(string='Material OK')
    capacity_ok = fields.Boolean(string='Capacity OK')
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
    ], default='draft', string='Status')
