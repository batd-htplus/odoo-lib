from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HtplusScheduleRun(models.Model):
    _name = 'htplus.schedule.run'
    _description = 'Schedule Run'
    _inherit = ['mail.thread', 'htplus.security.mixin']
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
        """Finish datetime using workcenter calendar when available."""
        calendar = workcenter.resource_calendar_id if workcenter else False
        if calendar and hasattr(calendar, 'plan_hours'):
            try:
                return calendar.plan_hours(hours, start, compute_leaves=True)
            except Exception:  # noqa: BLE001 - fall back to wall-clock hours
                pass
        return start + timedelta(hours=hours)

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
        cursors = {}
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
                wc_key = workcenter.id if workcenter else 0
                start = cursors.get(wc_key) or self._htplus_horizon_start()
                hours = self._htplus_duration_hours(workorder)
                end = self._htplus_plan_end(start, hours, workcenter)
                vals.update({
                    'date_start': start,
                    'date_finished': end,
                    'schedule_state': 'scheduled',
                    'schedule_conflict': False,
                    'capacity_ok': True,
                })
                cursors[wc_key] = end
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
        """Set schedule_conflict / capacity_ok for overlapping WOs on the same WC."""
        workorders.write({'schedule_conflict': False, 'capacity_ok': True})
        by_wc = {}
        for workorder in workorders.filtered(lambda w: w.date_start and w.state != 'cancel'):
            by_wc.setdefault(workorder.workcenter_id.id, self.env['mrp.workorder'])
            by_wc[workorder.workcenter_id.id] |= workorder

        conflicted = self.env['mrp.workorder']
        for wc_id, group in by_wc.items():
            ordered = group.sorted(lambda w: (w.date_start, w.id))
            for index, left in enumerate(ordered):
                left_end = left.date_finished or left.date_start
                for right in ordered[index + 1:]:
                    if right.date_start >= left_end:
                        break
                    conflicted |= left | right

            for workorder in ordered:
                end = workorder.date_finished or workorder.date_start
                outsiders = self.env['mrp.workorder'].search([
                    ('id', 'not in', group.ids),
                    ('workcenter_id', '=', wc_id),
                    ('date_start', '!=', False),
                    ('date_start', '<', end),
                    ('date_finished', '>', workorder.date_start),
                    ('schedule_state', 'in', ('confirmed', 'locked')),
                    ('state', '!=', 'cancel'),
                ], limit=1)
                if outsiders:
                    conflicted |= workorder

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
            run._htplus_mark_overlaps(run.workorder_ids)
            run.state = 'calculated'
        return True

    def action_confirm(self):
        """Confirm the run once it has no conflicts and every work order is dated."""
        self._htplus_require_planner()
        for run in self:
            if run.conflict_count:
                raise ValidationError(_('Cannot confirm a schedule with unresolved conflicts.'))
            undated = run.workorder_ids.filtered(
                lambda w: w.state != 'cancel' and not w.date_start
            )
            if undated:
                raise ValidationError(_(
                    'Cannot confirm: %s work order(s) still unscheduled.'
                ) % len(undated))
            run.workorder_ids.filtered(lambda w: w.state != 'cancel').write({
                'schedule_state': 'confirmed',
            })
            run.state = 'confirmed'

    def action_lock(self):
        """Lock the run and its work orders against further rescheduling."""
        self._htplus_require_manager()
        for run in self:
            run.workorder_ids.locked = True
            run.workorder_ids.schedule_state = 'locked'
            run.state = 'locked'

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

    def _htplus_ensure_shift_for_wo(self, workorder):
        """Find or create a production shift covering the WO window."""
        if not workorder.date_start:
            return self.env['htplus.production.shift']
        work_date = fields.Date.to_date(workorder.date_start)
        Shift = self.env['htplus.production.shift']
        domain = [
            ('date', '=', work_date),
            ('state', 'in', ('draft', 'confirmed')),
        ]
        if workorder.line_id:
            domain.append(('line_id', '=', workorder.line_id.id))
        elif workorder.workcenter_id:
            domain.append(('workcenter_id', '=', workorder.workcenter_id.id))
        shift = Shift.search(domain, limit=1)
        if shift:
            return shift

        Template = self.env['htplus.shift.template']
        template = Template.search([
            ('active', '=', True),
            ('line_id', '=', workorder.line_id.id),
        ], limit=1) if workorder.line_id else Template.browse()
        if not template and workorder.workcenter_id and 'factory_id' in workorder.workcenter_id._fields:
            factory = workorder.workcenter_id.factory_id
            if factory:
                template = Template.search([
                    ('active', '=', True),
                    ('factory_id', '=', factory.id),
                ], limit=1)
        if not template:
            template = Template.search([('active', '=', True)], limit=1)
        if not template:
            return Shift.browse()

        return Shift.create({
            'date': work_date,
            'template_id': template.id,
            'factory_id': template.factory_id.id or False,
            'plant_id': template.plant_id.id or False,
            'line_id': (workorder.line_id or template.line_id).id or False,
            'workcenter_id': workorder.workcenter_id.id or False,
            'manpower_required': template.default_manpower or 1,
        })

    def action_propose_workforce(self):
        """Create draft workforce assignments linking scheduled WOs to shifts."""
        self._htplus_require_planner()
        Assignment = self.env['htplus.workforce.assignment']
        created = Assignment.browse()
        for run in self:
            workorders = run.workorder_ids.filtered(
                lambda w: w.date_start and w.state != 'cancel' and not w.locked
            )
            if not workorders:
                raise UserError(_('No dated work orders to assign. Calculate or run the solver first.'))
            for workorder in workorders:
                existing = Assignment.search([
                    ('workorder_id', '=', workorder.id),
                    ('state', '!=', 'cancelled'),
                ], limit=1)
                if existing:
                    continue
                shift = run._htplus_ensure_shift_for_wo(workorder)
                if not shift:
                    continue
                employee = shift.leader_id
                if not employee:
                    employee = self.env['hr.employee'].search([
                        ('company_id', '=', run.user_id.company_id.id),
                    ], limit=1)
                if not employee:
                    continue
                assignment = Assignment.create({
                    'shift_id': shift.id,
                    'workorder_id': workorder.id,
                    'employee_id': employee.id,
                    'date_start': workorder.date_start,
                    'date_end': workorder.date_finished or workorder.date_start,
                    'qty': workorder.production_id.product_qty or 1.0,
                })
                assignment.action_validate()
                created |= assignment
        if not created:
            raise UserError(_(
                'No new assignments created. Need shift templates (and preferably a shift leader '
                'or employee) covering the work order dates.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Workforce Assignments'),
            'res_model': 'htplus.workforce.assignment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }


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
        """Build the gantt rows for the selected (or latest dated) work orders."""
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
                'write_date': fields.Datetime.to_string(workorder.write_date),
            })
        return rows

    def _htplus_check_optimistic_lock(self):
        """Refuse stale writes when client sends expected write_date(s).

        Context keys (either):
        - htplus_expected_write_date: single ISO datetime for a one-record write
        - htplus_expected_write_dates: {workorder_id: ISO datetime}
        """
        expected_map = self.env.context.get('htplus_expected_write_dates') or {}
        single = self.env.context.get('htplus_expected_write_date')
        if single and len(self) == 1:
            expected_map = {self.id: single}
        if not expected_map:
            return
        for workorder in self:
            expected = expected_map.get(workorder.id)
            if not expected or not workorder.write_date:
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
        """Enforce locked work orders, optimistic locking and schedule-change logging."""
        tracked = ('date_start', 'date_finished', 'machine_id', 'line_id', 'priority', 'schedule_state', 'locked')
        if any(field in vals for field in tracked) or self.env.context.get('htplus_expected_write_date') \
                or self.env.context.get('htplus_expected_write_dates'):
            self._htplus_check_optimistic_lock()
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
