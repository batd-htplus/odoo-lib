from odoo import api, fields, models, _


class HtplusScheduleRun(models.Model):
    _name = 'htplus.schedule.run'
    _description = 'Schedule Run'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(required=True, default=lambda self: _('New'))
    version = fields.Integer(default=1, string='Version')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('confirmed', 'Confirmed'),
        ('locked', 'Locked'),
    ], default='draft', string='Status', tracking=True)
    production_plan_id = fields.Many2one('htplus.production.plan', string='Production Plan')
    scenario_id = fields.Many2one('htplus.simulation.scenario', string='Simulation Scenario')
    algorithm = fields.Selection([
        ('manual', 'Manual'),
        ('rule_engine', 'Rule Engine'),
        ('solver_cpsat', 'Solver (CP-SAT)'),
    ], default='manual', string='Algorithm')
    date_start = fields.Date()
    date_end = fields.Date()
    conflict_count = fields.Integer(compute='_compute_conflict_count', string='Conflicts')
    workorder_ids = fields.One2many('mrp.workorder', 'schedule_run_id', string='Work Orders')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.schedule.run') or _('New')
        return super().create(vals_list)

    @api.depends('workorder_ids.schedule_conflict')
    def _compute_conflict_count(self):
        for run in self:
            run.conflict_count = len(run.workorder_ids.filtered(lambda w: w.schedule_conflict))

    def action_calculate(self):
        self.state = 'calculated'

    def action_confirm(self):
        for run in self:
            if run.conflict_count:
                raise models.ValidationError(_('Cannot confirm a schedule with unresolved conflicts.'))
            run.workorder_ids.schedule_state = 'confirmed'
            run.state = 'confirmed'

    def action_lock(self):
        for run in self:
            run.workorder_ids.locked = True
            run.workorder_ids.schedule_state = 'locked'
            run.state = 'locked'

    def action_undo_change(self):
        changes = self.env['htplus.schedule.change'].search([
            ('schedule_run_id', 'in', self.ids),
        ], order='id desc')
        if changes:
            change = changes[0]
            change.workorder_id[change.field] = change.old_value
            change.unlink()

    def action_run_solver(self):
        self.ensure_one()
        if not self.scenario_id:
            self.scenario_id = self.env['htplus.simulation.scenario'].create({
                'name': _('Solver run for %s', self.name),
                'base_schedule_run_id': self.id,
            }).id
        self.scenario_id.action_run()
        return self.scenario_id


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    htplus_plan_id = fields.Many2one('htplus.production.plan', string='Production Plan')
    htplus_plan_line_id = fields.Many2one('htplus.production.plan.line', string='Production Plan Line')
    schedule_run_ids = fields.Many2many('htplus.schedule.run', string='Schedule Runs')


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run')
    line_id = fields.Many2one('htplus.line', string='Line')
    machine_id = fields.Many2one('htplus.machine', string='Machine')
    schedule_start = fields.Datetime(string='Schedule Start')
    schedule_end = fields.Datetime(string='Schedule End')
    schedule_state = fields.Selection([
        ('unscheduled', 'Unscheduled'),
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('locked', 'Locked'),
    ], default='unscheduled', string='Schedule Status')
    locked = fields.Boolean(default=False)
    priority = fields.Integer(default=0)
    schedule_conflict = fields.Boolean(string='Conflict')
    material_ok = fields.Boolean(string='Material OK')
    capacity_ok = fields.Boolean(string='Capacity OK')
    machine_ok = fields.Boolean(string='Machine OK')

    def action_open_gantt(self):
        workorders = self.filtered(lambda w: w.schedule_start or w.schedule_state != 'unscheduled')
        if not workorders:
            workorders = self.search([('schedule_start', '!=', False)], limit=500)
        return [{
            'id': workorder.id,
            'workcenter_id': workorder.workcenter_id.name or '',
            'workorder_ref': workorder.name or '',
            'product_ref': workorder.product_id.display_name or '',
            'schedule_start': workorder.schedule_start.isoformat(),
            'schedule_end': (workorder.schedule_end or workorder.schedule_start).isoformat(),
            'locked': workorder.locked,
        } for workorder in workorders.sorted(lambda w: (w.schedule_start or w.create_date or fields.Datetime.now()))]

    def write(self, vals):
        res = super().write(vals)
        tracked = ('schedule_start', 'schedule_end', 'machine_id', 'line_id', 'priority')
        if any(field in vals for field in tracked):
            for workorder in self:
                self.env['htplus.schedule.change'].create({
                    'schedule_run_id': workorder.schedule_run_id.id or False,
                    'workorder_id': workorder.id,
                    'user_id': self.env.uid,
                    'field': next((f for f in tracked if f in vals), 'schedule_start'),
                    'old_value': None,
                    'new_value': None,
                })
        return res


class HtplusScheduleChange(models.Model):
    _name = 'htplus.schedule.change'
    _description = 'Schedule Change'
    _order = 'id desc'

    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run')
    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    field = fields.Selection([
        ('schedule_start', 'Schedule Start'),
        ('schedule_end', 'Schedule End'),
        ('machine_id', 'Machine'),
        ('line_id', 'Line'),
        ('priority', 'Priority'),
    ], required=True)
    old_value = fields.Char(string='Old Value')
    new_value = fields.Char(string='New Value')
    date_change = fields.Datetime(string='Changed At', default=fields.Datetime.now)
