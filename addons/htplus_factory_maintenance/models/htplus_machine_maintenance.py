from odoo import api, fields, models


class HtplusMachine(models.Model):
    """Link a production machine to the equipment Maintenance tracks.

    Deliberately a plain Many2one rather than ``_inherits`` delegation. A machine
    *has* a maintenance equipment record; it is not *a* maintenance equipment.
    Delegation would also pull the Maintenance access rules onto htplus.machine,
    so a shop-floor operator without the maintenance group could no longer read
    the machines they work on.
    """

    _inherit = 'htplus.machine'

    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Maintenance Equipment',
        ondelete='set null',
        help='Equipment record carrying MTBF, MTTR and maintenance requests. '
             'Optional: a machine without one simply has its status set by hand.',
    )
    open_request_count = fields.Integer(
        compute='_compute_open_request_count', string='Open Maintenance Requests')

    @api.depends('equipment_id')
    def _compute_open_request_count(self):
        """Count the maintenance requests still open on the linked equipment."""
        Request = self.env['maintenance.request']
        by_equipment = {}
        equipments = self.mapped('equipment_id')
        if equipments:
            grouped = Request._read_group(
                [('equipment_id', 'in', equipments.ids), ('stage_id.done', '=', False)],
                ['equipment_id'], ['__count'],
            )
            by_equipment = {equipment.id: count for equipment, count in grouped}
        for machine in self:
            machine.open_request_count = by_equipment.get(machine.equipment_id.id, 0)

    def action_open_maintenance_requests(self):
        """Open the maintenance requests of the linked equipment."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': 'maintenance.request',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.equipment_id.id)],
            'context': {'default_equipment_id': self.equipment_id.id},
        }
