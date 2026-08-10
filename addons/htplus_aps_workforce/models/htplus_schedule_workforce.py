from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HtplusScheduleRun(models.Model):
    """Workforce proposal driven by a schedule run.

    Lives in the bridge because it is the one place APS and Workforce meet:
    APS states what a scheduled work order needs, Workforce owns the assignment
    that answers it. Neither module references the other.
    """

    _inherit = 'htplus.schedule.run'

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

            # One lookup for every existing assignment instead of one per work order.
            assigned_wo_ids = set(
                Assignment.search([
                    ('workorder_id', 'in', workorders.ids),
                    ('state', '!=', 'cancelled'),
                ]).mapped('workorder_id').ids
            )
            pending = workorders.filtered(lambda w: w.id not in assigned_wo_ids)
            if not pending:
                continue

            # Resolve one shift per (date, line, work center) group instead of per work order.
            shift_by_group = {}
            employee_by_company = {}
            for workorder in pending:
                group = (
                    fields.Date.to_date(workorder.date_start),
                    workorder.line_id.id or 0,
                    workorder.workcenter_id.id or 0,
                )
                if group not in shift_by_group:
                    shift_by_group[group] = run._htplus_ensure_shift_for_wo(workorder)

            vals_list = []
            for workorder in pending:
                group = (
                    fields.Date.to_date(workorder.date_start),
                    workorder.line_id.id or 0,
                    workorder.workcenter_id.id or 0,
                )
                shift = shift_by_group.get(group)
                if not shift:
                    continue
                employee = shift.leader_id
                if not employee:
                    company_id = run.user_id.company_id.id
                    if company_id not in employee_by_company:
                        employee_by_company[company_id] = self.env['hr.employee'].search([
                            ('company_id', '=', company_id),
                        ], limit=1)
                    employee = employee_by_company[company_id]
                if not employee:
                    continue
                vals_list.append({
                    'shift_id': shift.id,
                    'workorder_id': workorder.id,
                    'employee_id': employee.id,
                    'date_start': workorder.date_start,
                    'date_end': workorder.date_finished or workorder.date_start,
                    'qty': workorder.production_id.product_qty or 1.0,
                })
            if vals_list:
                created |= Assignment.create(vals_list)
        created.action_validate()
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
            'context': {
                'default_date_start': self[:1].date_start,
            },
        }

    def action_open_assignments(self):
        """Open workforce assignments for work orders on this run."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Workforce Assignments'),
            'res_model': 'htplus.workforce.assignment',
            'view_mode': 'list,form',
            'domain': [('workorder_id', 'in', self.workorder_ids.ids)],
        }
