from datetime import timedelta

from odoo import api, fields, models, _
from .htplus_schedule_result import HtplusScheduleResult
from odoo.exceptions import UserError, ValidationError


class HtplusScheduleRun(models.Model):
    _name = 'htplus.schedule.run'
    _htplus_factory_path = 'production_plan_id.factory_id'
    _description = 'Schedule Run'
    _inherit = ['mail.thread', 'htplus.security.mixin', 'htplus.factory.scope.mixin',
                'htplus.workflow.mixin']

    _htplus_transitions = {
        'calculate': {'from': ('draft', 'calculated'), 'to': 'calculated', 'role': 'planner'},
        'confirm': {'from': ('calculated',), 'to': 'confirmed', 'role': 'planner'},
        'lock': {'from': ('confirmed',), 'to': 'locked', 'role': 'manager'},
        'reset': {'from': ('confirmed', 'locked'), 'to': 'calculated', 'role': 'manager'},
    }
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
    last_result = fields.Json(
        string='Last Scheduler Result', readonly=True, copy=False,
        help='The full ScheduleResult of the last scheduler run, kept so a plan '
             'can be explained after the fact.')
    last_explanation = fields.Text(
        string='Why This Schedule', readonly=True, copy=False)

    @api.depends('production_plan_id', 'production_plan_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a schedule run by the production plan it schedules."""
        return super()._compute_htplus_factory_id()

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
        """Count work orders flagged as schedule conflicts."""
        for run in self:
            run.conflict_count = len(run.workorder_ids.filtered(lambda w: w.schedule_conflict))

    def _htplus_horizon_start(self):
        """Earliest datetime of the scheduling horizon for this run."""
        self.ensure_one()
        if self.date_start:
            return fields.Datetime.to_datetime(self.date_start)
        plan = self.production_plan_id
        if plan and plan.date_start:
            return fields.Datetime.to_datetime(plan.date_start)
        return fields.Datetime.now()

    @staticmethod
    def _htplus_duration_hours(workorder):
        """Estimated duration in hours from the expected duration or order qty.

        Args:
            workorder: Work order to estimate.

        Returns:
            Duration in hours, at least 0.5.
        """
        if workorder.duration_expected:
            return max(float(workorder.duration_expected) / 60.0, 0.5)
        qty = workorder.production_id.product_qty if workorder.production_id else 1.0
        return max(float(qty or 1.0) / 10.0, 0.5)

    def _htplus_plan_end(self, start, hours, workcenter):
        """Finish datetime for a duration placed on a work center's calendar.

        Always goes through ``resource.calendar``. The previous version fell
        back to wall-clock arithmetic when anything went wrong, which produced a
        schedule that quietly ignored shifts, breaks and shutdowns - wrong dates
        that look right. A missing calendar is a configuration error and is
        reported as one, the same way ``mrp`` itself reports it.

        Args:
            start: Datetime the operation may begin.
            hours: Working hours needed.
            workcenter: Work center running the operation.

        Returns:
            Datetime the operation finishes, respecting working time.

        Raises:
            UserError: The work center has no working calendar.
        """
        calendar = workcenter.resource_calendar_id if workcenter else False
        if not calendar:
            raise UserError(_(
                'There is no defined calendar on workcenter %s. Set one before '
                'scheduling: without working hours the dates would be meaningless.',
                workcenter.display_name if workcenter else _('(none)'),
            ))
        return calendar.plan_hours(hours, start, compute_leaves=True)

    def _htplus_propose_slot(self, workorder, workcenter):
        """Find the first free slot on the work center for this work order.

        Delegates to ``mrp.workcenter._get_first_available_slot``, the same
        primitive ``button_plan`` uses. That matters for correctness, not just
        for reuse: it searches against the work center's *existing* leaves, so
        the slot is disjoint from every other planned work order - including
        ones this schedule run has never seen, and maintenance downtime.

        The previous implementation advanced a private per-work-center cursor
        held in memory for the duration of one run. It could only avoid
        collisions with work orders inside the same run, so two runs, or a run
        and a plain Odoo ``button_plan``, would happily book the same machine
        for the same hour.

        Args:
            workorder: Work order to place.
            workcenter: Work center that will run it.

        Returns:
            Tuple of (start, finish) datetimes.

        Raises:
            UserError: No calendar on the work center, or no slot within the
                horizon Odoo searches.
        """
        horizon_start = self._htplus_horizon_start()
        hours = self._htplus_duration_hours(workorder)
        if not workcenter:
            # No work center means no capacity to reserve; place it on the
            # horizon and let the conflict pass flag it.
            return horizon_start, horizon_start + timedelta(hours=hours)
        if not workcenter.resource_calendar_id:
            raise UserError(_(
                'There is no defined calendar on workcenter %s. Set one before '
                'scheduling: without working hours the dates would be meaningless.',
                workcenter.display_name,
            ))
        duration_minutes = workorder.duration_expected or hours * 60.0
        start, end = workcenter._get_first_available_slot(horizon_start, duration_minutes)
        if not start:
            # Odoo returns (False, reason) when it finds nothing in ~700 days.
            raise UserError(_(
                'No free slot on workcenter %(wc)s for %(wo)s: %(reason)s',
                wc=workcenter.display_name, wo=workorder.display_name, reason=end,
            ))
        return start, end

    def _htplus_split_attachable(self, workorders):
        """Return (attachable, blocked) — blocked = locked or on confirmed/locked run."""
        self.ensure_one()
        attachable = self.env['mrp.workorder']
        blocked = self.env['mrp.workorder']
        for workorder in workorders:
            other = workorder.schedule_run_id
            if workorder.locked:
                blocked |= workorder
            elif other and other != self and other.state in ('confirmed', 'locked'):
                blocked |= workorder
            else:
                attachable |= workorder
        return attachable, blocked

    def _htplus_attach_workorders(self, workorders, propose_dates=True):
        """Link WOs to this run; optionally propose non-overlapping dates per WC."""
        self.ensure_one()
        if self.state not in ('draft', 'calculated'):
            raise UserError(_('Only draft/calculated schedule runs can attach work orders.'))
        attachable, blocked = self._htplus_split_attachable(workorders)
        if blocked:
            raise UserError(_(
                'Cannot take work orders from a confirmed/locked schedule (or locked WO): %s'
            ) % ', '.join(blocked[:5].mapped('display_name')))
        if not attachable:
            raise UserError(_('No attachable work orders.'))

        Machine = self.env['htplus.machine']
        ordered = attachable.sorted(lambda w: (-(w.priority or 0), w.id))
        for workorder in ordered:
            vals = {'schedule_run_id': self.id}
            plan_line = workorder.production_id.htplus_plan_line_id
            if plan_line:
                vals['priority'] = plan_line.priority or 0
            workcenter = workorder.workcenter_id
            if workcenter and 'line_id' in workcenter._fields and workcenter.line_id:
                vals['line_id'] = workcenter.line_id.id
            if workcenter and not workorder.machine_id:
                machine = Machine.search([('workcenter_id', '=', workcenter.id)], limit=1)
                if machine:
                    vals['machine_id'] = machine.id

            if propose_dates and not workorder.date_start:
                start, end = self._htplus_propose_slot(workorder, workcenter)
                vals.update({
                    'date_start': start,
                    'date_finished': end,
                    'schedule_state': 'scheduled',
                    'schedule_conflict': False,
                    'capacity_ok': True,
                })
            elif workorder.date_start:
                vals['schedule_state'] = (
                    workorder.schedule_state
                    if workorder.schedule_state != 'unscheduled'
                    else 'scheduled'
                )
            else:
                vals['schedule_state'] = 'unscheduled'
            workorder.write(vals)
        return True

    def action_load_workorders_from_plan(self):
        """Reload attachable WOs from the linked production plan into this draft run."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft schedule runs can reload work orders.'))
        plan = self.production_plan_id
        if not plan:
            raise UserError(_('Set a production plan on this schedule run first.'))
        workorders = plan.production_ids.filtered(
            lambda p: p.state != 'cancel'
        ).mapped('workorder_ids').filtered(lambda w: w.state != 'cancel')
        if not workorders:
            raise UserError(_('No work orders found on the production plan.'))
        self._htplus_attach_workorders(workorders, propose_dates=True)
        return True

    def _htplus_mark_overlaps(self, workorders):
        """Flag work orders that share a work center with an overlapping one.

        Delegates to ``mrp.workorder._get_conflicted_workorder_ids()``, which
        answers this in one SQL statement using PostgreSQL's OVERLAPS. The
        previous implementation grouped in Python, compared every pair inside a
        group, and then issued one extra search per work order to catch overlaps
        with work orders outside the run - quadratic in the run and linear in
        queries, for a question the database answers directly.

        Reusing Odoo's method also means HTPlus and plain ``button_plan`` agree
        on what a conflict is, instead of each having its own opinion.

        Args:
            workorders: Work orders to evaluate and flag.

        Returns:
            The recordset that turned out to be in conflict.
        """
        workorders.write({'schedule_conflict': False, 'capacity_ok': True})
        candidates = workorders.filtered(lambda w: w.date_start and w.state != 'cancel')
        if not candidates:
            return self.env['mrp.workorder']
        conflicted_map = candidates._get_conflicted_workorder_ids()
        conflicted = self.env['mrp.workorder'].browse(
            [workorder_id for workorder_id in conflicted_map if conflicted_map[workorder_id]]
        )
        if conflicted:
            conflicted.write({'schedule_conflict': True, 'capacity_ok': False})
        return conflicted

    def action_calculate(self):
        """Detect overlapping work orders and mark the run as calculated."""
        self._htplus_require_planner()
        for run in self:
            if run.state not in ('draft', 'calculated'):
                raise UserError(_('Only draft/calculated runs can be recalculated.'))
            dated = run.workorder_ids.filtered(lambda w: w.date_start)
            if not dated:
                # Baseline rule-engine dates when none proposed yet.
                undated = run.workorder_ids.filtered(
                    lambda w: w.state != 'cancel' and not w.date_start and not w.locked
                )
                if undated:
                    run._htplus_attach_workorders(undated, propose_dates=True)
                dated = run.workorder_ids.filtered(lambda w: w.date_start)
            if not dated:
                raise UserError(_('No dated work orders to calculate. Attach or run the solver first.'))
            run._htplus_store_result(run._htplus_run_scheduler())
            run._htplus_mark_overlaps(run.workorder_ids)
            run._htplus_apply_transition('calculate')
            run._htplus_snapshot_proposals()
        return True

    def _htplus_guard_confirm(self):
        """A run may only be confirmed when it is complete and conflict-free."""
        if self.conflict_count:
            raise ValidationError(_('Cannot confirm a schedule with unresolved conflicts.'))
        undated = self.workorder_ids.filtered(
            lambda w: w.state != 'cancel' and not w.date_start
        )
        if undated:
            raise ValidationError(_(
                'Cannot confirm: %s work order(s) still unscheduled.'
            ) % len(undated))

    def _htplus_after_confirm(self):
        """Carry the confirmation down to the work orders of the run."""
        self.workorder_ids.filtered(lambda w: w.state != 'cancel').write({
            'schedule_state': 'confirmed',
        })

    def _htplus_after_lock(self):
        """Lock the work orders of the run against further rescheduling."""
        self.workorder_ids.locked = True
        self.workorder_ids.schedule_state = 'locked'

    def _htplus_after_reset(self):
        """Release the work orders so the run can be recalculated."""
        self.workorder_ids.with_context(htplus_force_locked_write=True).write({
            'locked': False,
            'schedule_state': 'scheduled',
        })

    def action_undo_change(self):
        """Revert the most recent schedule change recorded on this run."""
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
        """Run the solver, storing results in a simulation scenario."""
        self.ensure_one()
        self._htplus_require_planner()
        if not self.scenario_id:
            self.scenario_id = self.env['htplus.simulation.scenario'].create({
                'name': _('Solver run for %s', self.name),
                'base_schedule_run_id': self.id,
            }).id
        self.scenario_id.action_run()
        return self.scenario_id

    def _htplus_resolve_scheduler(self, algorithm=None):
        """Resolve which solver should handle this run. HOOK CÔNG KHAI (§5.3).

        Core only knows ``rule_engine`` and ``solver_cpsat``; any other value
        (including ``manual``) falls back to ``rule_engine``. Dự án cắm engine
        riêng bằng cách ``_inherit`` và override method này (kèm ``selection_add``
        trên field ``algorithm``) — không phải sửa whitelist cứng ở core/bridge.
        """
        self.ensure_one()
        algorithm = algorithm or self.algorithm
        return algorithm if algorithm in ('rule_engine', 'solver_cpsat') else 'rule_engine'

    def _htplus_run_scheduler(self, algorithm=None):
        """Produce a ScheduleResult for this run.

        HOOK - this is the seam §5.3 describes. Core ships the rule engine;
        a project plugs in another by overriding this (plus ``selection_add`` on
        ``algorithm``) and returning the same contract. Nothing downstream needs
        to know which engine answered.

        Args:
            algorithm: Override the run's own algorithm.

        Returns:
            HtplusScheduleResult covering every work order of the run.
        """
        self.ensure_one()
        code = self._htplus_resolve_scheduler(algorithm)
        result = HtplusScheduleResult(
            algorithm=code,
            explanation=_(
                'Rule engine: work orders placed in priority order, each on the '
                'first free slot of its work center calendar.'),
            objective={'name': 'first_fit', 'value': 0.0},
        )
        ordered = self.workorder_ids.sorted(lambda w: (-(w.priority or 0), w.id))
        for workorder in ordered:
            if workorder.state == 'cancel':
                result.add_unassigned(workorder.id, _('Work order is cancelled.'))
                continue
            if workorder.locked:
                result.add_assignment(
                    workorder.id, workorder.date_start, workorder.date_finished,
                    workcenter_id=workorder.workcenter_id.id,
                    machine_id=workorder.machine_id.id, line_id=workorder.line_id.id)
                continue
            if not workorder.workcenter_id:
                result.add_unassigned(workorder.id, _('No work center on the work order.'))
                continue
            try:
                start, end = self._htplus_propose_slot(workorder, workorder.workcenter_id)
            except UserError as error:
                result.add_unassigned(workorder.id, str(error))
                continue
            result.add_assignment(
                workorder.id, start, end,
                workcenter_id=workorder.workcenter_id.id,
                machine_id=workorder.machine_id.id, line_id=workorder.line_id.id)
        result.metadata['workorder_count'] = len(self.workorder_ids)
        return result

    def _htplus_store_result(self, result):
        """Record a ScheduleResult on the run after checking it answers fully.

        Args:
            result: HtplusScheduleResult returned by a scheduler.

        Raises:
            UserError: The result does not account for every work order, or
                omits the algorithm or explanation.
        """
        self.ensure_one()
        problems = result.validate(self.workorder_ids.ids)
        if problems:
            raise UserError(_(
                'The scheduler returned an incomplete result:\n- %s'
            ) % '\n- '.join(problems))
        self.write({
            'algorithm': result.algorithm,
            'last_result': result.to_dict(),
            'last_explanation': result.explanation,
        })
        return True

    def action_open_production_plan(self):
        self.ensure_one()
        if not self.production_plan_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Plan'),
            'res_model': 'htplus.production.plan',
            'res_id': self.production_plan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_gantt(self):
        self.ensure_one()
        if not self.workorder_ids:
            raise UserError(_('No work orders on this schedule run.'))
        ctx = {'htplus_schedule_run_id': self.id}
        if self.production_plan_id:
            ctx['htplus_production_plan_id'] = self.production_plan_id.id
        return {
            'type': 'ir.actions.client',
            'tag': 'htplus_aps_core.gantt',
            'name': _('Gantt — %s') % self.name,
            'context': ctx,
        }

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    htplus_plan_id = fields.Many2one('htplus.production.plan', string='Production Plan')
    htplus_plan_line_id = fields.Many2one('htplus.production.plan.line', string='Production Plan Line')
    schedule_run_ids = fields.Many2many('htplus.schedule.run', string='Schedule Runs')


class MrpWorkorder(models.Model):
    _name = 'mrp.workorder'
    _inherit = ['mrp.workorder', 'htplus.factory.scope.mixin', 'htplus.concurrency.mixin']
    _htplus_factory_path = 'workcenter_id.factory_id'
    _htplus_concurrency_fields = ('date_start', 'date_finished', 'machine_id', 'line_id',
                                  'priority', 'schedule_state', 'locked')

    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run', index=True)
    line_id = fields.Many2one('htplus.line', string='Line')
    machine_id = fields.Many2one('htplus.machine', string='Machine')
    schedule_state = fields.Selection([
        ('unscheduled', 'Unscheduled'),
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('locked', 'Locked'),
    ], default='unscheduled', string='Schedule Status', index=True)
    locked = fields.Boolean(default=False, index=True)
    priority = fields.Integer(default=0)
    schedule_conflict = fields.Boolean(string='Conflict', index=True)
    material_ok = fields.Boolean(string='Material OK')
    capacity_ok = fields.Boolean(string='Capacity OK')
    machine_ok = fields.Boolean(string='Machine OK')

    @api.depends('workcenter_id', 'workcenter_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a work order by the work center that runs it."""
        return super()._compute_htplus_factory_id()


    @api.model
    def action_open_gantt(self):
        """Build the gantt payload grouped by production line.

        Optional context keys:
            htplus_production_plan_id — limit to MOs of that production plan
            htplus_schedule_run_id — limit to work orders on that schedule run
            htplus_gantt_date_start / htplus_gantt_date_end — time window;
                only work orders overlapping the window are returned
            htplus_gantt_line_ids — limit to those production lines
        """
        domain = [('date_start', '!=', False), ('state', '!=', 'cancel')]
        plan_id = self.env.context.get('htplus_production_plan_id')
        run_id = self.env.context.get('htplus_schedule_run_id')
        if run_id:
            domain.append(('schedule_run_id', '=', int(run_id)))
        elif plan_id:
            domain.append(('production_id.htplus_plan_id', '=', int(plan_id)))
        line_ids = self.env.context.get('htplus_gantt_line_ids')
        if line_ids:
            domain.append(('line_id', 'in', [int(x) for x in line_ids]))
        date_from = self.env.context.get('htplus_gantt_date_start')
        date_to = self.env.context.get('htplus_gantt_date_end')
        if date_from and date_to:
            domain.append(('date_start', '<=', date_to))
            domain.append(('date_finished', '>=', date_from))
        total = self.search_count(domain)
        workorders = self.search(domain)
        if not workorders:
            return {'start': False, 'end': False, 'lines': [], 'workorders': [], 'total': total}
        workorders = workorders.sorted(
            lambda w: (w.date_start or w.create_date or fields.Datetime.now()))
        lines = []
        for line in workorders.mapped('line_id').filtered(lambda l: l.active).sorted('code'):
            lines.append({
                'id': line.id,
                'name': line.display_name,
                'machine': line.machine_ids[:1].name or '',
            })
        if any(not workorder.line_id for workorder in workorders):
            lines.append({'id': 0, 'name': 'Unassigned', 'machine': ''})
        bars = []
        for workorder in workorders:
            if not workorder.date_start:
                continue
            end = workorder.date_finished or workorder.date_start
            bars.append({
                'id': workorder.id,
                'line_id': workorder.line_id.id or 0,
                'workcenter_id': workorder.workcenter_id.name or '',
                'workorder_ref': workorder.name or '',
                'product_ref': workorder.product_id.display_name or '',
                'date_start': workorder.date_start.isoformat(),
                'date_finished': end.isoformat(),
                'locked': workorder.locked,
                'conflict': workorder.schedule_conflict,
                'write_date': fields.Datetime.to_string(workorder.write_date),
            })
        start = min(workorder.date_start for workorder in workorders)
        end = max((workorder.date_finished or workorder.date_start)
                  for workorder in workorders)
        return {
            'start': start.isoformat(),
            'end': end.isoformat(),
            'lines': lines,
            'workorders': bars,
            'total': total,
        }

    @api.model
    def action_save_gantt_move(self, moves):
        """Persist drag / resize / re-line moves sent by the gantt.

        Args:
            moves: List of dicts (or a single dict) with work order id, new
                start/end, optional line_id and expected write_date.

        Returns:
            The refreshed gantt payload (respects htplus_* context filters).
        """
        if isinstance(moves, dict):
            moves = [moves]
        if not moves:
            return self.action_open_gantt()
        moves_by_id = {int(move['id']): move for move in moves}
        workorders = self.browse(list(moves_by_id))
        for workorder in workorders:
            if workorder.locked:
                raise UserError(_(
                    'Work order "%s" is locked and cannot be rescheduled.'
                ) % workorder.display_name)
        for workorder in workorders:
            expected = moves_by_id[workorder.id].get('write_date')
            if not expected:
                continue
            expected_dt = fields.Datetime.to_datetime(expected)
            if expected_dt and workorder.write_date.replace(microsecond=0) != expected_dt.replace(microsecond=0):
                raise UserError(_(
                    'Work order "%(wo)s" was modified by another user (%(when)s). '
                    'Reload and try again.'
                ) % {
                    'wo': workorder.display_name,
                    'when': fields.Datetime.to_string(workorder.write_date),
                })
        for workorder in workorders:
            move = moves_by_id[workorder.id]
            vals = {}
            for field in ('date_start', 'date_finished'):
                if move.get(field):
                    raw = move[field].replace('T', ' ')
                    # JS may send trailing Z / milliseconds.
                    raw = raw.replace('Z', '').split('.')[0]
                    vals[field] = fields.Datetime.to_datetime(raw)
            if vals.get('date_start') and vals.get('date_finished'):
                # The base mrp.workorder.write recomputes date_finished from the
                # calendar when both dates are set; passing a consistent
                # duration_expected keeps the requested window intact.
                vals['duration_expected'] = workorder._calculate_duration_expected(
                    date_start=vals['date_start'],
                    date_finished=vals['date_finished'])
            line_id = move.get('line_id')
            if line_id is not None and int(line_id) and int(line_id) != workorder.line_id.id:
                line = self.env['htplus.line'].browse(int(line_id))
                if line.exists():
                    vals['line_id'] = line.id
                    if line.workcenter_ids:
                        vals['workcenter_id'] = line.workcenter_ids[:1].id
            if vals:
                workorder.write(vals)
        conflicted = self._htplus_refresh_conflicts(workorders)
        payload = self.action_open_gantt()
        payload['saved'] = len(workorders)
        payload['conflicted'] = len(conflicted)
        return payload

    def _htplus_refresh_conflicts(self, workorders):
        """Recompute schedule_conflict for the moved WOs and their neighbours."""
        workorders.write({'schedule_conflict': False, 'capacity_ok': True})
        candidates = self.env['mrp.workorder']
        for workorder in workorders.filtered(lambda w: w.date_start and w.state != 'cancel'):
            candidates |= workorder
            candidates |= self.env['mrp.workorder'].search([
                ('workcenter_id', '=', workorder.workcenter_id.id),
                ('date_start', '!=', False),
                ('state', '!=', 'cancel'),
            ])
        candidates = candidates.filtered(lambda w: w.date_start and w.state != 'cancel')
        by_wc = {}
        for workorder in candidates:
            by_wc.setdefault(workorder.workcenter_id.id, self.env['mrp.workorder'])
            by_wc[workorder.workcenter_id.id] |= workorder
        conflicted = self.env['mrp.workorder']
        for group in by_wc.values():
            ordered = group.sorted(lambda w: (w.date_start, w.id))
            for index, left in enumerate(ordered):
                left_end = left.date_finished or left.date_start
                for right in ordered[index + 1:]:
                    if right.date_start >= left_end:
                        break
                    conflicted |= left | right
        if conflicted:
            conflicted.write({'schedule_conflict': True, 'capacity_ok': False})
        return conflicted


    @staticmethod
    def _htplus_change_value(value):
        """Serialize a field value (datetime, record or scalar) for change logs.

        Args:
            value: Field value to serialize.

        Returns:
            A comparable string, or None for empty values.
        """
        if value is False or value is None:
            return None
        if hasattr(value, 'id'):
            return str(value.id) if value else None
        return str(value)

    def write(self, vals):
        """Enforce locked work orders and log schedule changes.

        The staleness check lives in htplus.concurrency.mixin and runs from its
        own write(); this override only adds what is specific to scheduling.
        """
        for workorder in self:
            if workorder.locked and any(f in vals for f in ('date_start', 'date_finished', 'machine_id', 'line_id')):
                if not self.env.context.get('htplus_force_locked_write'):
                    raise UserError(_(
                        'Work order "%s" is locked and cannot be rescheduled.'
                    ) % workorder.display_name)
        pending = []
        if any(field in vals for field in ('date_start', 'date_finished', 'machine_id', 'line_id', 'priority')):
            for workorder in self:
                if not workorder.schedule_run_id:
                    continue
                for field in ('date_start', 'date_finished', 'machine_id', 'line_id', 'priority'):
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
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'schedule_run_id.factory_id'
    _description = 'Schedule Change'
    _order = 'id desc'

    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run', index=True)
    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order', index=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    @api.depends('schedule_run_id', 'schedule_run_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope an audit row by the run it belongs to."""
        return super()._compute_htplus_factory_id()

    field = fields.Selection([
        ('date_start', 'Start'),
        ('date_finished', 'Finished'),
        ('machine_id', 'Machine'),
        ('line_id', 'Line'),
        ('priority', 'Priority'),
    ], required=True)
    old_value = fields.Char(string='Old Value')
    new_value = fields.Char(string='New Value')
    date_change = fields.Datetime(string='Changed At', default=fields.Datetime.now, index=True)

    def action_cleanup_old_changes(self, days=90):
        """Delete change logs older than the given age to bound audit growth.

        Args:
            days: Keep logs younger than this many days.
        """
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        self.search([('date_change', '<', cutoff)]).unlink()
        return True
