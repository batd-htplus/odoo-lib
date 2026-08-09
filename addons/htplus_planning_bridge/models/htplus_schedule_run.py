from odoo import fields, models, _
from odoo.exceptions import UserError


class HtplusScheduleRun(models.Model):
    _inherit = 'htplus.schedule.run'

    def action_run_solver(self):
        """Call the planning engine and store the schedule result in a simulation scenario.

        Does not write mrp.workorder dates — apply via scenario.action_apply().
        The manual algorithm keeps the local copy-from-base behaviour.
        """
        self.ensure_one()
        if self.algorithm == 'manual':
            return super().action_run_solver()

        if not self.workorder_ids:
            raise UserError(_('Add work orders to the schedule run before running the solver.'))

        algorithm = self.algorithm if self.algorithm in ('rule_engine', 'solver_cpsat') else 'rule_engine'
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
        self.state = 'calculated'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Simulation Scenario'),
            'res_model': 'htplus.simulation.scenario',
            'res_id': scenario.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
            'capacity': center.capacity,
        } for center in centers]

    @staticmethod
    def _htplus_parse_dt(value):
        """Convert a string datetime from the planning engine to a datetime value."""
        if not value:
            return False
        return fields.Datetime.to_datetime(value)
