from odoo import _, api, fields, models


class HtplusFactory(models.Model):
    _name = 'htplus.factory'
    _description = 'Factory'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    plant_ids = fields.One2many('htplus.plant', 'factory_id', string='Plants')
    workcenter_ids = fields.One2many('mrp.workcenter', 'factory_id', string='Work Centers')
    resource_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Working Hours',
        help='Odoo resource calendar used by work centers in this factory '
             '(shift patterns and factory holidays sync here).',
    )
    holiday_ids = fields.One2many('htplus.factory.holiday', 'factory_id', string='Factory Holidays')
    active = fields.Boolean(default=True)

    def _ensure_resource_calendar(self):
        """Return the factory working-hours calendar, creating it if needed.

        Returns:
            The factory's resource.calendar record.
        """
        self.ensure_one()
        if self.resource_calendar_id:
            return self.resource_calendar_id
        calendar = self.env['resource.calendar'].create({
            'name': _('Factory %s', self.name),
            'company_id': self.company_id.id,
            'attendance_ids': [(5, 0, 0)],
        })
        self.with_context(htplus_skip_wc_calendar=True).write({
            'resource_calendar_id': calendar.id,
        })
        return calendar

    def action_apply_calendar_to_workcenters(self):
        """Apply the factory working-hours calendar to all its work centers."""
        for factory in self:
            calendar = factory._ensure_resource_calendar()
            factory.workcenter_ids.write({'resource_calendar_id': calendar.id})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """Create the factories and give each one a working-hours calendar."""
        factories = super().create(vals_list)
        for factory in factories:
            factory._ensure_resource_calendar()
        return factories


class HtplusPlant(models.Model):
    _name = 'htplus.plant'
    _description = 'Plant'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    factory_id = fields.Many2one('htplus.factory', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', related='factory_id.company_id', store=True)
    line_ids = fields.One2many('htplus.line', 'plant_id', string='Lines')
    workcenter_ids = fields.One2many('mrp.workcenter', 'plant_id', string='Work Centers')
    active = fields.Boolean(default=True)


class HtplusLine(models.Model):
    _name = 'htplus.line'
    _description = 'Production Line'
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    plant_id = fields.Many2one('htplus.plant', required=True, ondelete='cascade')
    factory_id = fields.Many2one('htplus.factory', related='plant_id.factory_id', store=True, index=True)
    workcenter_ids = fields.One2many('mrp.workcenter', 'line_id', string='Work Centers')
    machine_ids = fields.One2many('htplus.machine', 'line_id', string='Machines')
    active = fields.Boolean(default=True)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    factory_id = fields.Many2one('htplus.factory', index=True)
    plant_id = fields.Many2one('htplus.plant')
    line_id = fields.Many2one('htplus.line')

    @api.onchange('factory_id')
    def _onchange_htplus_factory_calendar(self):
        """Carry the factory calendar onto the work center when the factory changes."""
        for wc in self:
            if wc.factory_id and wc.factory_id.resource_calendar_id:
                wc.resource_calendar_id = wc.factory_id.resource_calendar_id

    @api.model_create_multi
    def create(self, vals_list):
        """Default the calendar from the factory when creating work centers without one."""
        for vals in vals_list:
            if vals.get('factory_id') and not vals.get('resource_calendar_id'):
                factory = self.env['htplus.factory'].browse(vals['factory_id'])
                calendar = factory._ensure_resource_calendar()
                vals['resource_calendar_id'] = calendar.id
        return super().create(vals_list)

    def write(self, vals):
        """Resync work center calendars whenever their factory changes."""
        res = super().write(vals)
        if self.env.context.get('htplus_skip_wc_calendar'):
            return res
        if 'factory_id' in vals:
            for wc in self.filtered('factory_id'):
                calendar = wc.factory_id._ensure_resource_calendar()
                if wc.resource_calendar_id != calendar:
                    super(MrpWorkcenter, wc).write({'resource_calendar_id': calendar.id})
        return res
