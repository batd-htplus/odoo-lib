from odoo import api, fields, models


class HtplusSimulationScenario(models.Model):
    _name = 'htplus.simulation.scenario'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'base_schedule_run_id.factory_id'
    _description = 'Simulation Scenario'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', related='factory_id.company_id', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status')
    base_schedule_run_id = fields.Many2one('htplus.schedule.run', string='Base Schedule Run', check_company=True)

    @api.depends('base_schedule_run_id', 'base_schedule_run_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a scenario by the schedule run it branches from."""
        return super()._compute_htplus_factory_id()

    scenario_date = fields.Date(default=fields.Date.context_today)
    overtime_hours = fields.Float(string='Overtime (hours)')
    capacity_change_pct = fields.Float(string='Capacity Change (%)')
    manpower_change_pct = fields.Float(string='Manpower Change (%)')
    cost_multiplier = fields.Float(string='Cost Multiplier', default=1.0)
    include_holiday = fields.Boolean(string='Include Holidays')
    line_ids = fields.One2many('htplus.simulation.line', 'scenario_id', string='Lines')
    total_delay_hours = fields.Float(compute='_compute_totals', string='Total Delay (hours)')
    total_cost = fields.Float(compute='_compute_totals', string='Total Cost')
    active = fields.Boolean(default=True)

    @api.depends('line_ids.delay_hours', 'line_ids.cost')
    def _compute_totals(self):
        """Sum delay and cost across the scenario lines."""
        for scenario in self:
            scenario.total_delay_hours = sum(scenario.line_ids.mapped('delay_hours'))
            scenario.total_cost = sum(scenario.line_ids.mapped('cost'))

    def action_copy_from_base(self):
        """Seed scenario lines from the base schedule run's work orders."""
        for scenario in self:
            if not scenario.base_schedule_run_id:
                continue
            vals = []
            for workorder in scenario.base_schedule_run_id.workorder_ids:
                vals.append((0, 0, {
                    'workorder_id': workorder.id,
                    'machine_id': workorder.machine_id.id or False,
                    'original_start': workorder.date_start,
                    'original_end': workorder.date_finished,
                }))
            scenario.line_ids = vals
            scenario.state = 'computed'

    def action_run(self):
        """Compute simulated dates for every scenario line."""
        for scenario in self:
            if not scenario.line_ids:
                scenario.action_copy_from_base()
            for line in scenario.line_ids:
                start = line.original_start
                end = line.original_end
                if end and start:
                    line.simulated_start = start
                    line.simulated_end = end
            scenario.state = 'computed'
        return True

    def action_apply(self):
        """Write simulated dates onto the real work orders and mark the scenario applied."""
        # Materialise simulation lines onto real work orders only on apply.
        for scenario in self:
            for line in scenario.line_ids.filtered(lambda l: l.simulated_start):
                line.workorder_id.write({
                    'date_start': line.simulated_start,
                    'date_finished': line.simulated_end,
                })
            scenario.state = 'applied'


class HtplusSimulationLine(models.Model):
    _name = 'htplus.simulation.line'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'scenario_id.factory_id'
    _description = 'Simulation Line'
    _check_company_auto = True

    scenario_id = fields.Many2one('htplus.simulation.scenario', required=True, ondelete='cascade', check_company=True)
    company_id = fields.Many2one('res.company', related='factory_id.company_id', store=True)

    @api.depends('scenario_id', 'scenario_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a simulation line by its scenario."""
        return super()._compute_htplus_factory_id()

    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    machine_id = fields.Many2one('htplus.machine', string='Machine', check_company=True)
    original_start = fields.Datetime(string='Original Start')
    original_end = fields.Datetime(string='Original End')
    simulated_start = fields.Datetime(string='Simulated Start')
    simulated_end = fields.Datetime(string='Simulated End')

    @api.depends('simulated_end', 'original_end')
    def _compute_delay(self):
        """Delay in hours when the simulated end runs past the original end."""
        for line in self:
            delay = 0.0
            if line.simulated_end and line.original_end:
                delta = line.simulated_end - line.original_end
                delay = delta.total_seconds() / 3600.0
            line.delay_hours = max(delay, 0.0)

    delay_hours = fields.Float(compute='_compute_delay', string='Delay (hours)')
    cost = fields.Float(string='Cost')
