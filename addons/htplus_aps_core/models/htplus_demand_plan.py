from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HtplusDemandPlan(models.Model):
    _name = 'htplus.demand.plan'
    _description = 'Demand Plan'
    _inherit = ['mail.thread', 'htplus.workflow.mixin', 'htplus.factory.scope.mixin']
    _order = 'date_start desc'

    _htplus_transitions = {
        'confirm': {'from': ('draft',), 'to': 'confirmed', 'role': 'planner'},
        'approve': {'from': ('confirmed',), 'to': 'approved', 'role': 'manager'},
        'plan': {'from': ('approved',), 'to': 'planned', 'role': 'planner'},
        'cancel': {'from': ('draft', 'confirmed', 'approved'), 'to': 'cancelled',
                   'role': 'planner'},
        'reset': {'from': ('cancelled',), 'to': 'draft', 'role': 'manager'},
    }

    name = fields.Char(required=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('planned', 'Planned'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)
    factory_id = fields.Many2one(
        'htplus.factory', string='Factory', index=True,
        default=lambda self: self._htplus_default_factory(),
        help='Factory this plan is for. Required from Confirm onwards - a plan '
             'nobody can attribute to a site cannot be scheduled against real capacity.')
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
    production_plan_ids = fields.One2many(
        'htplus.production.plan', 'demand_plan_id', string='Production Plans')
    production_plan_count = fields.Integer(
        compute='_compute_production_plan_count', string='Production Plans')
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.model
    def _htplus_default_factory(self):
        """Preselect the factory when the user is scoped to exactly one.

        Returns:
            htplus.factory recordset, empty when the choice is ambiguous.
        """
        allowed = self.env.user.htplus_factory_ids
        return allowed if len(allowed) == 1 else self.env['htplus.factory']

    def _htplus_require_factory(self):
        """Refuse to move a plan forward while it has no factory."""
        missing = self.filtered(lambda plan: not plan.factory_id)
        if missing:
            raise UserError(_(
                'Set a factory on %(names)s before confirming: without it the plan '
                'is outside every access scope and cannot be scheduled.',
                names=', '.join(missing.mapped('display_name')),
            ))

    def _htplus_guard_confirm(self):
        """A demand plan must name its factory before it can be confirmed."""
        self._htplus_require_factory()

    def _compute_production_plan_count(self):
        for rec in self:
            rec.production_plan_count = len(rec.production_plan_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.demand.plan') or _('New')
        return super().create(vals_list)

    def action_open_production_plans(self):
        """Open production plans generated from this demand plan."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Production Plans'),
            'res_model': 'htplus.production.plan',
            'view_mode': 'list,form',
            'domain': [('demand_plan_id', '=', self.id)],
            'context': {'default_demand_plan_id': self.id},
        }
        if len(self.production_plan_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.production_plan_ids.id
        return action

    def _htplus_add_plan_line(self, plan, product, qty, deadline, demand_line=False, priority=0, seen=None):
        """Add a production plan line and explode manufactured components (multi-level).

        Args:
            plan: Production plan to add the line to.
            product: Product to produce.
            qty: Quantity to produce.
            deadline: Required completion date.
            demand_line: Source demand line, if any.
            priority: Line priority.
            seen: Set of already-queued (product, deadline) keys.
        """
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

    def _htplus_guard_plan(self):
        """Refuse to mark the demand as planned when it has no lines."""
        if not self.line_ids:
            raise UserError(_('Cannot generate a production plan from an empty demand plan.'))

    def action_generate_plan(self):
        """Generate the production plan from the demand lines."""
        self.ensure_one()
        # Checked up front as well as in the transition guard: building the plan
        # first and failing afterwards would be wasted work.
        self._htplus_require_role('planner')
        self._htplus_guard_plan()
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
        self._htplus_apply_transition('plan')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Plan'),
            'res_model': 'htplus.production.plan',
            'res_id': plan.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_demand_plan_id': self.id},
        }

    def action_export_excel(self):
        """Trigger the .xlsx export of this demand plan."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/htplus/aps/demand/export?plan_id=%s' % self.id,
            'target': 'self',
        }


class HtplusDemandPlanLine(models.Model):
    _name = 'htplus.demand.plan.line'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'plan_id.factory_id'
    _description = 'Demand Plan Line'
    _order = 'date, sequence'

    plan_id = fields.Many2one('htplus.demand.plan', required=True, ondelete='cascade')

    @api.depends('plan_id', 'plan_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a demand line by its plan."""
        return super()._compute_htplus_factory_id()

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
