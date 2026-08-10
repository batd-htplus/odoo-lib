from odoo import models


class MaintenanceRequest(models.Model):
    """Reflect maintenance work onto machine status and workcenter availability.

    This is the loop neither Odoo CE nor Enterprise wires up: a machine under
    repair should stop being schedulable. Opening a request drops the machine to
    'maintenance'; closing it restores 'operational'.
    """

    _inherit = 'maintenance.request'

    def _htplus_machines(self):
        """Return the HTPlus machines linked to these requests."""
        equipments = self.mapped('equipment_id')
        if not equipments:
            return self.env['htplus.machine']
        return self.env['htplus.machine'].search([('equipment_id', 'in', equipments.ids)])

    def _htplus_sync_machine_status(self):
        """Set machine status from the open/closed state of its requests."""
        for machine in self._htplus_machines():
            open_requests = self.search_count([
                ('equipment_id', '=', machine.equipment_id.id),
                ('stage_id.done', '=', False),
            ])
            if open_requests and machine.status == 'operational':
                machine.status = 'maintenance'
            elif not open_requests and machine.status == 'maintenance':
                machine.status = 'operational'

    def create(self, vals_list):
        """Sync machine status when a request is raised."""
        requests = super().create(vals_list)
        requests._htplus_sync_machine_status()
        return requests

    def write(self, vals):
        """Sync machine status when a request moves stage or changes equipment."""
        result = super().write(vals)
        if 'stage_id' in vals or 'equipment_id' in vals:
            self._htplus_sync_machine_status()
        return result
