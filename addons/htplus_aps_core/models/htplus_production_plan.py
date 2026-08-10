from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HtplusProductionPlan(models.Model):
    _name = 'htplus.production.plan'
    _description = 'Production Plan'
    _inherit = ['mail.thread', 'htplus.workflow.mixin', 'htplus.factory.scope.mixin']
    _order = 'date_start desc'

    _htplus_transitions = {
        'confirm': {'from': ('draft',), 'to': 'confirmed', 'role': 'planner'},
        'approve': {'from': ('confirmed',), 'to': 'approved', 'role': 'manager'},
        'lock': {'from': ('confirmed', 'approved'), 'to': 'locked', 'role': 'manager'},
        'cancel': {'from': ('draft', 'confirmed', 'approved'), 'to': 'cancelled',
                   'role': 'planner'},
        'reset': {'from': ('cancelled',), 'to': 'draft', 'role': 'manager'},
    }

    name = fields.Char(required=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)
    demand_plan_id = fields.Many2one('htplus.demand.plan', string='Demand Plan')
    factory_id = fields.Many2one(
        'htplus.factory', string='Factory', index=True,
        default=lambda self: self._htplus_default_factory(),
        help='Factory this plan is for. Required from Confirm onwards - a plan '
             'nobody can attribute to a site cannot be scheduled against real capacity.')

    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    line_ids = fields.One2many('htplus.production.plan.line', 'plan_id', string='Lines')
    production_ids = fields.One2many('mrp.production', 'htplus_plan_id', string='Manufacturing Orders')
    schedule_run_ids = fields.One2many('htplus.schedule.run', 'production_plan_id', string='Schedule Runs')
    schedule_run_count = fields.Integer(compute='_compute_link_counts', string='Schedule Runs')
    production_count = fields.Integer(compute='_compute_link_counts', string='Manufacturing Orders')
    workorder_count = fields.Integer(compute='_compute_link_counts', string='Work Orders')
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
        """A production plan must name its factory before it can be confirmed."""
        self._htplus_require_factory()

    @api.onchange('demand_plan_id')
    def _onchange_htplus_demand_plan_factory(self):
        """Inherit the factory from the demand plan this one answers."""
        if self.demand_plan_id.factory_id:
            self.factory_id = self.demand_plan_id.factory_id

    def _compute_link_counts(self):
        for plan in self:
            plan.schedule_run_count = len(plan.schedule_run_ids)
            plan.production_count = len(plan.production_ids)
            plan.workorder_count = len(plan.production_ids.mapped('workorder_ids'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.production.plan') or _('New')
        return super().create(vals_list)

    def _htplus_guard_approve(self):
        """Re-check material availability before the plan can be approved."""
        self.line_ids.action_check_materials()

    def action_check_materials(self):
        """Re-run the material availability check on all plan lines."""
        self._htplus_require_role('planner')
        self.line_ids.action_check_materials()
        return True

    def action_open_demand_plan(self):
        self.ensure_one()
        if not self.demand_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Demand Plan'),
            'res_model': 'htplus.demand.plan',
            'res_id': self.demand_plan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_productions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manufacturing Orders'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('htplus_plan_id', '=', self.id)],
            'context': {'default_htplus_plan_id': self.id},
        }

    def action_open_schedule_runs(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Schedule Runs'),
            'res_model': 'htplus.schedule.run',
            'view_mode': 'list,form',
            'domain': [('production_plan_id', '=', self.id)],
            'context': {
                'default_production_plan_id': self.id,
                'default_date_start': self.date_start,
                'default_date_end': self.date_end,
            },
        }
        if len(self.schedule_run_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.schedule_run_ids.id
        return action

    def action_open_gantt(self):
        """Open Gantt filtered to this production plan's work orders."""
        self.ensure_one()
        workorders = self.production_ids.mapped('workorder_ids').filtered(
            lambda w: w.state != 'cancel'
        )
        if not workorders:
            raise UserError(_(
                'No work orders on this plan. Create manufacturing orders first.'
            ))
        return {
            'type': 'ir.actions.client',
            'tag': 'htplus_aps_core.gantt',
            'name': _('Gantt — %s') % self.name,
            'context': {'htplus_production_plan_id': self.id},
        }

    def action_open_latest_schedule(self):
        """Open the newest schedule run, or create one when none exists."""
        self.ensure_one()
        if self.schedule_run_ids:
            run = self.schedule_run_ids.sorted('id', reverse=True)[:1]
            return {
                'type': 'ir.actions.act_window',
                'name': _('Schedule Run'),
                'res_model': 'htplus.schedule.run',
                'res_id': run.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return self.action_create_schedule()

    def action_use_on_dashboard(self):
        """Set this plan as the working plan on the APS dashboard."""
        self.ensure_one()
        Dashboard = self.env['htplus.dashboard.kpi']
        dash = Dashboard.search([], limit=1)
        if not dash:
            dash = Dashboard.create({'name': _('Production Dashboard')})
        dash.production_plan_id = self.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dashboard'),
            'res_model': 'htplus.dashboard.kpi',
            'res_id': dash.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_productions(self):
        """Create and confirm a manufacturing order for each plan line."""
        self._htplus_require_role('planner')
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

    def action_create_schedule(self):
        """Create a schedule run and attach work orders from this plan's MOs."""
        self.ensure_one()
        self._htplus_require_role('planner')
        if self.state in ('draft', 'cancelled'):
            raise UserError(_('Confirm and approve the production plan before scheduling.'))
        productions = self.production_ids.filtered(lambda p: p.state != 'cancel')
        if not productions:
            raise UserError(_(
                'No manufacturing orders on this plan. '
                'Use "Create Manufacturing Orders" first.'
            ))
        workorders = productions.mapped('workorder_ids').filtered(lambda w: w.state != 'cancel')
        if not workorders:
            raise UserError(_(
                'No work orders found. Confirm MOs that use a BOM with operations.'
            ))

        run = self.env['htplus.schedule.run'].create({
            'production_plan_id': self.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'algorithm': 'rule_engine',
            'version': len(self.schedule_run_ids) + 1,
        })
        # Attach proposes dates + refuses WOs on confirmed/locked runs.
        run._htplus_attach_workorders(workorders, propose_dates=True)
        run.action_calculate()
        self.line_ids.filtered(lambda l: l.production_id and l.state == 'confirmed').write({
            'state': 'planned',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Schedule Run'),
            'res_model': 'htplus.schedule.run',
            'res_id': run.id,
            'view_mode': 'form',
            'target': 'current',
        }


class HtplusProductionPlanLine(models.Model):
    _name = 'htplus.production.plan.line'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'plan_id.factory_id'
    _description = 'Production Plan Line'
    _order = 'date_deadline, sequence'

    plan_id = fields.Many2one('htplus.production.plan', required=True, ondelete='cascade')

    @api.depends('plan_id', 'plan_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a production line by its plan."""
        return super()._compute_htplus_factory_id()

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
        """Return the line BOM, falling back to the product default."""
        self.ensure_one()
        if self.bom_id:
            return self.bom_id
        bom = self.env['mrp.bom']._bom_find(
            self.product_id, company_id=self.plan_id.company_id.id, bom_type='normal'
        ).get(self.product_id)
        return bom or self.env['mrp.bom']

    def action_check_materials(self):
        """Check component stock against the BOM and flag shortages."""
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
            ctx = {}
            if line.date_deadline:
                ctx['to_date'] = line.date_deadline
            warehouse_ids = self.env['stock.warehouse'].search([
                ('company_id', '=', company.id),
            ]).ids
            if warehouse_ids:
                ctx['warehouse'] = warehouse_ids
            for bom_line, line_data in lines_done:
                product = bom_line.product_id.with_company(company)
                need = line_data.get('qty', 0.0)
                available = product.with_context(ctx).qty_available
                if available < need:
                    shortages.append('%s (need %.2f / have %.2f)' % (
                        product.display_name, need, available))
            line.material_ok = not shortages
            line.material_note = '; '.join(shortages[:3]) if shortages else _('OK')
        return True

    @api.onchange('product_id')
    def _onchange_product_id_bom(self):
        """Default the UoM and BOM from the selected product."""
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.bom_id = self._get_bom()
