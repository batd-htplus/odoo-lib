from odoo import fields, models, _
from odoo.addons.htplus_aps_core.models.htplus_schedule_result import HtplusScheduleResult
from odoo.exceptions import UserError


class HtplusScheduleRun(models.Model):
    _inherit = 'htplus.schedule.run'

    job_id = fields.Many2one('htplus.job', string='Background Job', readonly=True)

    def action_run_solver(self):
        """Call the planning engine and store the schedule result in a simulation scenario.

        Does not write mrp.workorder dates — apply via scenario.action_apply().
        The manual algorithm keeps the local copy-from-base behaviour.
        """
        self.ensure_one()
        if self.algorithm == 'manual':
            return super().action_run_solver()
        return self._htplus_execute_solver()

    def action_run_solver_async(self):
        """Enqueue the solver as a background job instead of blocking the UI.

        Returns:
            True once the job is created; follow it on the run's job_id field.
        """
        self.ensure_one()
        if self.algorithm == 'manual':
            raise UserError(_('The manual algorithm cannot run in the background.'))
        if self.state not in ('draft', 'calculated'):
            raise UserError(_(
                'Only draft/calculated schedule runs can run the solver. %s is "%s".'
            ) % (self.display_name, self.state))
        if not self.workorder_ids:
            raise UserError(_('Add work orders to the schedule run before running the solver.'))
        job = self.env['htplus.job']._enqueue(
            'htplus.schedule.run',
            '_htplus_solver_job',
            payload={'run_id': self.id},
            name=_('Solver run for %s', self.name),
            origin_model=self._name,
            origin_id=self.id,
        )
        self.job_id = job.id
        return True

    def _htplus_solver_job(self, run_id):
        """Job body: execute the solver for the given run id and store the scenario."""
        run = self.browse(run_id)
        run._htplus_execute_solver()
        return run.scenario_id.id

    def _htplus_execute_solver(self):
        """Run the engine solver synchronously and write the simulation scenario."""
        self.ensure_one()
        if self.state not in ('draft', 'calculated'):
            raise UserError(_(
                'Only draft/calculated schedule runs can run the solver. %s is "%s".'
            ) % (self.display_name, self.state))
        if not self.workorder_ids:
            raise UserError(_('Add work orders to the schedule run before running the solver.'))

        algorithm = self._htplus_resolve_scheduler()
        workorders = [self._htplus_wo_payload(wo) for wo in self.workorder_ids]
        constraints = {
            'workcenters': self._htplus_workcenter_constraints(),
            'lock_workorder_ids': self.workorder_ids.filtered('locked').ids,
            'holidays': [],
            'rules': {},
        }

        service = self.env['htplus.planning.service']
        submit = service.schedule_recommend(
            workorders, constraints, objective='min_tardiness', algorithm=algorithm,
        )
        job_id = submit.get('job_id')
        if not job_id:
            raise UserError(_('Planning engine did not return a job id.'))

        result = service.wait_job(job_id)
        schedule_result = (result.get('data') or {}).get('schedule_result') or []
        by_id = {entry['workorder_id']: entry for entry in schedule_result}

        scenario = self.scenario_id
        if not scenario:
            scenario = self.env['htplus.simulation.scenario'].create({
                'name': _('Solver run for %s', self.name),
                'base_schedule_run_id': self.id,
            })
            self.scenario_id = scenario

        scenario.line_ids.unlink()
        line_vals = []
        for workorder in self.workorder_ids:
            entry = by_id.get(workorder.id, {})
            line_vals.append((0, 0, {
                'workorder_id': workorder.id,
                'machine_id': workorder.machine_id.id or False,
                'original_start': workorder.date_start,
                'original_end': workorder.date_finished,
                'simulated_start': self._htplus_parse_dt(entry.get('date_start')),
                'simulated_end': self._htplus_parse_dt(entry.get('date_finished')),
                'cost': entry.get('delay_hours') or 0.0,
            }))
        scenario.write({'line_ids': line_vals, 'state': 'computed'})
        self._htplus_apply_transition('calculate')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Simulation Scenario'),
            'res_model': 'htplus.simulation.scenario',
            'res_id': scenario.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _htplus_run_scheduler(self, algorithm=None):
        """Ask the planning engine, and answer in the same contract as core.

        Overrides the built-in rule engine when the run asks for a real solver.
        Everything the engine leaves out is filled in here rather than silently
        dropped: a work order the engine did not return comes back as
        ``unassigned`` with a reason, and the response's own ``algorithm`` label
        is trusted over the request's, so a degraded fallback shows up as what
        it actually was.
        """
        self.ensure_one()
        code = self._htplus_resolve_scheduler(algorithm)
        if code == 'rule_engine':
            return super()._htplus_run_scheduler(algorithm)

        payload = [self._htplus_wo_payload(wo) for wo in self.workorder_ids]
        constraints = {
            'workcenters': self._htplus_workcenter_constraints(),
            'lock_workorder_ids': self.workorder_ids.filtered('locked').ids,
            'holidays': [],
            'rules': {},
        }
        service = self.env['htplus.planning.service']
        submit = service.schedule_recommend(
            payload, constraints, objective='min_tardiness', algorithm=code)
        job_id = submit.get('job_id')
        if not job_id:
            raise UserError(_('Planning engine did not return a job id.'))
        response = service.wait_job(job_id)
        data = response.get('data') or {}
        entries = data.get('schedule_result') or []

        result = HtplusScheduleResult(
            algorithm=data.get('algorithm') or code,
            explanation=data.get('explanation') or _(
                'Planning engine %s returned a schedule for %s work order(s).',
                data.get('algorithm') or code, len(entries)),
            objective=data.get('objective') or {},
            metadata={'job_id': job_id, 'engine_returned': len(entries)},
        )
        by_id = {entry.get('workorder_id'): entry for entry in entries}
        for workorder in self.workorder_ids:
            entry = by_id.get(workorder.id)
            start = self._htplus_parse_dt((entry or {}).get('date_start'))
            end = self._htplus_parse_dt((entry or {}).get('date_finished'))
            if not entry:
                result.add_unassigned(workorder.id, _('The engine returned no slot for it.'))
            elif not start or not end:
                result.add_unassigned(
                    workorder.id,
                    entry.get('reason') or _('The engine returned no dates for it.'))
            else:
                result.add_assignment(
                    workorder.id, start, end,
                    workcenter_id=workorder.workcenter_id.id,
                    machine_id=workorder.machine_id.id,
                    line_id=workorder.line_id.id)
                if entry.get('delay_hours'):
                    result.add_conflict(
                        workorder.id, 'tardiness',
                        _('%s hour(s) late against the deadline.', entry['delay_hours']))
        return result

    def _htplus_wo_payload(self, workorder):
        """Build the work order payload dict sent to the planning engine."""
        production = workorder.production_id
        qty = production.product_qty if production else 1.0
        due = False
        if production and production.date_deadline:
            due = fields.Datetime.to_string(production.date_deadline)
        return {
            'workorder_id': workorder.id,
            'product_id': workorder.product_id.id,
            'qty': qty,
            'routing': [workorder.workcenter_id.id] if workorder.workcenter_id else [],
            'due': due,
            'priority': workorder.priority or 0,
        }

    def _htplus_workcenter_constraints(self):
        """Build the work center constraints dict for the schedule run's work orders."""
        centers = self.workorder_ids.mapped('workcenter_id')
        return [{
            'workcenter_id': center.id,
            'name': center.name,
            # mrp.workcenter carries default_capacity; plain `capacity` lives on
            # mrp.workcenter.capacity, the per-product override model.
            'capacity': center.default_capacity,
        } for center in centers]

    @staticmethod
    def _htplus_parse_dt(value):
        """Convert a string datetime from the planning engine to a datetime value."""
        if not value:
            return False
        return fields.Datetime.to_datetime(value)
