from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
        self.line_ids.action_check_materials()
        self.state = 'approved'

    def action_lock(self):
        self.state = 'locked'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_check_materials(self):
        self.line_ids.action_check_materials()
        return True

    def action_create_productions(self):
        for plan in self:
            plan.line_ids.action_check_materials()
            missing = plan.line_ids.filtered(lambda l: l.state == 'draft' and not l.material_ok)
            if missing:
                raise UserError(_(
                    'Material check failed for: %s. Resolve stock or BOM before creating MOs.'
                ) % ', '.join(missing.mapped('product_id.display_name')))
            for line in plan.line_ids.filtered(lambda l: l.state == 'draft'):
                bom = line._get_bom()
                if not bom:
                    raise UserError(_(
                        'No Bill of Materials for %s. Set a BOM on the product or plan line.'
                    ) % line.product_id.display_name)
                production = self.env['mrp.production'].create({
                    'product_id': line.product_id.id,
                    'product_qty': line.qty,
                    'product_uom_id': line.uom_id.id,
                    'bom_id': bom.id,
                    'date_deadline': line.date_deadline,
                    'company_id': plan.company_id.id,
                    'htplus_plan_id': plan.id,
                    'htplus_plan_line_id': line.id,
                })
                production.action_confirm()
                line.write({
                    'production_id': production.id,
                    'bom_id': bom.id,
                    'state': 'confirmed',
                })
        return True


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
    bom_id = fields.Many2one('mrp.bom', string='BOM', domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    product_tmpl_id = fields.Many2one(
        related='product_id.product_tmpl_id', store=True, readonly=True)
    priority = fields.Integer(default=0)
    workcenter_ids = fields.Many2many('mrp.workcenter', string='Work Centers')
    material_ok = fields.Boolean(string='Material OK', copy=False)
    capacity_ok = fields.Boolean(string='Capacity OK', copy=False)
    material_note = fields.Char(string='Material Note', copy=False)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
    ], default='draft', string='Status')

    def _get_bom(self):
        self.ensure_one()
        if self.bom_id:
            return self.bom_id
        bom = self.env['mrp.bom']._bom_find(
            self.product_id, company_id=self.plan_id.company_id.id, bom_type='normal'
        ).get(self.product_id)
        return bom or self.env['mrp.bom']

    def action_check_materials(self):
        for line in self:
            bom = line._get_bom()
            if not bom:
                line.material_ok = False
                line.material_note = _('No BOM')
                continue
            if not line.bom_id:
                line.bom_id = bom.id
            try:
                _boms_done, lines_done = bom.explode(line.product_id, line.qty or 0.0)
            except Exception as error:  # noqa: BLE001 - surface as line note
                line.material_ok = False
                line.material_note = str(error)
                continue
            shortages = []
            company = line.plan_id.company_id
            for bom_line, line_data in lines_done:
                product = bom_line.product_id.with_company(company)
                need = line_data.get('qty', 0.0)
                available = product.qty_available
                if available < need:
                    shortages.append('%s (need %.2f / have %.2f)' % (
                        product.display_name, need, available))
            line.material_ok = not shortages
            line.material_note = '; '.join(shortages[:3]) if shortages else _('OK')
        return True

    @api.onchange('product_id')
    def _onchange_product_id_bom(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.bom_id = self._get_bom()
