from odoo import fields, models, _


class HtplusWorkforceAssignment(models.Model):
    _inherit = 'htplus.workforce.assignment'

    actual_id = fields.Many2one(
        'htplus.workorder.actual',
        string='Shop Floor Actual',
        copy=False,
        readonly=True,
    )

    def _htplus_after_confirm(self):
        """Open the matching shop-floor actual once the assignment is confirmed.

        Hooked into the transition rather than wrapping action_confirm, so the
        actual is created on exactly the records that really changed state.
        """
        parent = getattr(super(), '_htplus_after_confirm', None)
        if parent:
            parent()
        self._htplus_open_mes_actual()

    def _htplus_open_mes_actual(self):
        """Link confirmed assignment to a MES actual for the assigned employee."""
        Actual = self.env['htplus.workorder.actual']
        for assignment in self.filtered(lambda a: a.workorder_id and a.state == 'confirmed'):
            if assignment.actual_id and assignment.actual_id.state != 'finished':
                continue
            existing = Actual.search([
                ('workorder_id', '=', assignment.workorder_id.id),
                ('employee_id', '=', assignment.employee_id.id),
                ('state', 'in', ('draft', 'running', 'paused')),
            ], limit=1)
            if existing:
                assignment.actual_id = existing.id
                continue
            # Ready for operator: paused so we never violate single-running constraint.
            other_running = Actual.search_count([
                ('workorder_id', '=', assignment.workorder_id.id),
                ('state', '=', 'running'),
            ])
            actual = Actual.create({
                'workorder_id': assignment.workorder_id.id,
                'employee_id': assignment.employee_id.id,
                'machine_id': assignment.workorder_id.machine_id.id or False,
                'date_start': assignment.date_start or fields.Datetime.now(),
                'state': 'paused' if other_running else 'running',
            })
            assignment.actual_id = actual.id

    def action_open_actual(self):
        """Open the linked shop-floor actual for this assignment.

        Returns:
            the window action to open the actual, or False if none.
        """
        self.ensure_one()
        if not self.actual_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shop Floor Actual'),
            'res_model': 'htplus.workorder.actual',
            'res_id': self.actual_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
