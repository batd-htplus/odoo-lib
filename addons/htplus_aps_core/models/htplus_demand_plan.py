from odoo import api, fields, models, _


class HtplusDemandPlan(models.Model):
    _name = 'htplus.demand.plan'
    _description = 'Demand Plan'
    _inherit = ['mail.thread', 'htplus.security.mixin']
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
        self._htplus_require_planner()
        self.state = 'confirmed'

    def action_approve(self):
        self._htplus_require_manager()
        self.state = 'approved'

    def action_cancel(self):
        self._htplus_require_planner()
        self.state = 'cancelled'

    def _htplus_add_plan_line(self, plan, product, qty, deadline, demand_line=False, priority=0, seen=None):
        """Add a production plan line and explode manufactured components (multi-level)."""
        self.ensure_one()
        seen = seen if seen is not None else set()
        key = (product.id, fields.Date.to_string(deadline) if deadline else '')
        if key in seen:
            # Same product/deadline already queued — accumulate qty on existing line.
            existing = plan.line_ids.filtered(
                lambda l: l.product_id == product and l.date_deadline == deadline
            )[:1]
            if existing:
                existing.qty += qty
            return
        seen.add(key)

        Bom = self.env['mrp.bom']
        bom = Bom._bom_find(
            product, company_id=self.company_id.id, bom_type='normal'
        ).get(product)
        plan.write({'line_ids': [(0, 0, {
            'demand_line_id': demand_line.id if demand_line else False,
            'product_id': product.id,
            'qty': qty,
            'uom_id': product.uom_id.id,
            'date_deadline': deadline,
            'bom_id': bom.id if bom else False,
            'priority': priority,
        })]})

        if not bom:
            return
        try:
            _boms_done, lines_done = bom.explode(product, qty or 0.0)
        except Exception:  # noqa: BLE001
            return
        for bom_line, line_data in lines_done:
            component = bom_line.product_id
            need = line_data.get('qty', 0.0)
            if need <= 0:
                continue
            child_bom = Bom._bom_find(
                component, company_id=self.company_id.id, bom_type='normal'
            ).get(component)
            if child_bom:
                child_deadline = deadline
                if deadline:
                    child_deadline = fields.Date.subtract(deadline, days=1)
                self._htplus_add_plan_line(
                    plan, component, need, child_deadline, demand_line=demand_line,
                    priority=priority, seen=seen,
                )

    def action_generate_plan(self):
        self.ensure_one()
        self._htplus_require_planner()
        plan = self.env['htplus.production.plan'].create({
            'demand_plan_id': self.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
        })
        for line in self.line_ids:
            self._htplus_add_plan_line(
                plan, line.product_id, line.qty, line.date,
                demand_line=line, priority=0,
            )
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
