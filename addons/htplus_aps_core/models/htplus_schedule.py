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
        ], order='id desc', limit=1)
        if not changes:
            return
        change = changes[0]
        field = change.field
        workorder = change.workorder_id
        if field in ('date_start', 'date_finished'):
            workorder[field] = fields.Datetime.to_datetime(change.old_value) if change.old_value else False
        elif field in ('machine_id', 'line_id'):
            workorder[field] = int(change.old_value) if change.old_value else False
        elif field == 'priority':
            workorder.priority = int(change.old_value or 0)
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
    # Planned window = Odoo date_start / date_finished (resource.calendar.leaves).
    # Do not reintroduce schedule_start/schedule_end — that was a shadow schedule.
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
        workorders = self.filtered(lambda w: w.date_start or w.schedule_state != 'unscheduled')
        if not workorders:
            workorders = self.search([('date_start', '!=', False)], limit=500)
        rows = []
        for workorder in workorders.sorted(
            lambda w: (w.date_start or w.create_date or fields.Datetime.now())
        ):
            if not workorder.date_start:
                continue
            end = workorder.date_finished or workorder.date_start
            rows.append({
                'id': workorder.id,
                'workcenter_id': workorder.workcenter_id.name or '',
                'workorder_ref': workorder.name or '',
                'product_ref': workorder.product_id.display_name or '',
                'date_start': workorder.date_start.isoformat(),
                'date_finished': end.isoformat(),
                'locked': workorder.locked,
            })
        return rows

    @staticmethod
    def _htplus_change_value(value):
        if value is False or value is None:
            return None
        if hasattr(value, 'id'):
            return str(value.id) if value else None
        return str(value)

    def write(self, vals):
        tracked = ('date_start', 'date_finished', 'machine_id', 'line_id', 'priority')
        pending = []
        if any(field in vals for field in tracked):
            for workorder in self:
                if not workorder.schedule_run_id:
                    continue
                for field in tracked:
                    if field not in vals:
                        continue
                    old_value = self._htplus_change_value(workorder[field])
                    new_value = self._htplus_change_value(vals[field])
                    if old_value == new_value:
                        continue
                    pending.append({
                        'schedule_run_id': workorder.schedule_run_id.id,
                        'workorder_id': workorder.id,
                        'user_id': self.env.uid,
                        'field': field,
                        'old_value': old_value,
                        'new_value': new_value,
                    })
        res = super().write(vals)
        if pending:
            self.env['htplus.schedule.change'].create(pending)
        if 'date_start' in vals or 'date_finished' in vals:
            for workorder in self.filtered(lambda w: w.date_start and w.schedule_state == 'unscheduled'):
                workorder.schedule_state = 'scheduled'
        return res


class HtplusScheduleChange(models.Model):
    _name = 'htplus.schedule.change'
    _description = 'Schedule Change'
    _order = 'id desc'

    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run')
    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    field = fields.Selection([
        ('date_start', 'Start'),
        ('date_finished', 'Finished'),
        ('machine_id', 'Machine'),
        ('line_id', 'Line'),
        ('priority', 'Priority'),
    ], required=True)
    old_value = fields.Char(string='Old Value')
    new_value = fields.Char(string='New Value')
    date_change = fields.Datetime(string='Changed At', default=fields.Datetime.now)
