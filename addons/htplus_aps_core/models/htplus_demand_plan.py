from odoo import api, fields, models, _


class HtplusDemandPlan(models.Model):
    _name = 'htplus.demand.plan'
    _description = 'Demand Plan'
    _inherit = ['mail.thread']
    _order = 'date_start desc'

    name = fields.Char(required=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('planned', 'Planned'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    source = fields.Selection([
        ('manual', 'Manual'),
        ('import', 'Import'),
        ('forecast', 'Forecast'),
        ('ai', 'Demand Forecast'),
    ], default='manual', string='Source')
    planning_forecast_id = fields.Many2one('htplus.planning.forecast', string='Demand Forecast')
    line_ids = fields.One2many('htplus.demand.plan.line', 'plan_id', string='Lines')
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.demand.plan') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.state = 'confirmed'

    def action_approve(self):
        self.state = 'approved'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_generate_plan(self):
        self.ensure_one()
        plan = self.env['htplus.production.plan'].create({
            'demand_plan_id': self.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
        })
        Bom = self.env['mrp.bom']
        for line in self.line_ids:
            bom = Bom._bom_find(
                line.product_id, company_id=self.company_id.id, bom_type='normal'
            ).get(line.product_id)
            plan.line_ids = [(0, 0, {
                'demand_line_id': line.id,
                'product_id': line.product_id.id,
                'qty': line.qty,
                'uom_id': line.uom_id.id,
                'date_deadline': line.date,
                'bom_id': bom.id if bom else False,
            })]
        self.state = 'planned'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.production.plan',
            'res_id': plan.id,
            'view_mode': 'form',
        }

    def action_export_excel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/htplus/aps/demand/export?plan_id=%s' % self.id,
            'target': 'self',
        }


class HtplusDemandPlanLine(models.Model):
    _name = 'htplus.demand.plan.line'
    _description = 'Demand Plan Line'
    _order = 'date, sequence'

    plan_id = fields.Many2one('htplus.demand.plan', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', required=True)
    date = fields.Date(required=True)
    qty = fields.Float(required=True)
    uom_id = fields.Many2one('uom.uom', required=True, default=lambda self: self.env['uom.uom']._get_default_uom_id())
    forecast_confidence = fields.Float(string='Forecast Confidence')
    remark = fields.Char()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
    ], default='draft', string='Status')
