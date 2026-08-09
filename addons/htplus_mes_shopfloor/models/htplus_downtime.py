from odoo import api, fields, models


class HtplusDowntimeReason(models.Model):
    _name = 'htplus.downtime.reason'
    _description = 'Downtime Reason'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    category = fields.Selection([
        ('breakdown', 'Breakdown'),
        ('setup', 'Setup'),
        ('wait_material', 'Waiting Material'),
        ('wait_machine', 'Waiting Machine'),
        ('wait_manpower', 'Waiting Manpower'),
        ('power', 'Power Outage'),
        ('quality', 'Quality'),
        ('other', 'Other'),
    ], default='other')
    active = fields.Boolean(default=True)

    def _mrp_loss_xmlid(self):
        """Return the Odoo block reason XML id matching the reason category.

        Returns:
            the mrp block_reason XML id for the category.
        """
        self.ensure_one()
        mapping = {
            'breakdown': 'mrp.block_reason1',
            'setup': 'mrp.block_reason2',
            'wait_material': 'mrp.block_reason0',
            'wait_machine': 'mrp.block_reason1',
            'wait_manpower': 'mrp.block_reason0',
            'power': 'mrp.block_reason1',
            'quality': 'mrp.block_reason5',
            'other': 'mrp.block_reason0',
        }
        return mapping.get(self.category, 'mrp.block_reason0')


class HtplusDowntime(models.Model):
    _name = 'htplus.downtime'
    _description = 'Downtime'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    machine_id = fields.Many2one('htplus.machine', string='Machine')
    reason_id = fields.Many2one('htplus.downtime.reason', required=True, string='Reason')
    type = fields.Selection([
        ('planned', 'Planned'),
        ('unplanned', 'Unplanned'),
    ], default='unplanned')
    date_start = fields.Datetime(required=True, string='Start')
    date_end = fields.Datetime(string='End')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    cost = fields.Float()
    productivity_id = fields.Many2one(
        'mrp.workcenter.productivity',
        string='Odoo Time Log',
        copy=False,
        readonly=True,
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        """Compute the downtime duration in minutes from start to end."""
        for rec in self:
            if rec.date_end and rec.date_start:
                delta = rec.date_end - rec.date_start
                rec.duration_minutes = delta.total_seconds() / 60.0
            else:
                rec.duration_minutes = 0.0

    duration_minutes = fields.Float(compute='_compute_duration', string='Duration (minutes)')

    def _workcenter(self):
        """Resolve the work center from the work order or the machine.

        Returns:
            the work center record, or an empty recordset if none.
        """
        self.ensure_one()
        if self.workorder_id.workcenter_id:
            return self.workorder_id.workcenter_id
        if self.machine_id.workcenter_id:
            return self.machine_id.workcenter_id
        return self.env['mrp.workcenter']

    def _sync_productivity(self):
        """Mirror each downtime as an mrp.workcenter.productivity time log."""
        Productivity = self.env['mrp.workcenter.productivity']
        for rec in self:
            workcenter = rec._workcenter()
            loss = self.env.ref(rec.reason_id._mrp_loss_xmlid(), raise_if_not_found=False)
            if not workcenter or not loss:
                continue
            vals = {
                'workcenter_id': workcenter.id,
                'workorder_id': rec.workorder_id.id or False,
                'loss_id': loss.id,
                'date_start': rec.date_start,
                'date_end': rec.date_end,
                'company_id': rec.company_id.id,
                'description': rec.reason_id.display_name,
            }
            user = rec.employee_id.user_id
            if user:
                vals['user_id'] = user.id
            if rec.productivity_id:
                rec.productivity_id.write(vals)
            else:
                productivity = Productivity.create(vals)
                rec.with_context(htplus_skip_productivity_sync=True).write({
                    'productivity_id': productivity.id,
                })

    @api.model_create_multi
    def create(self, vals_list):
        """Create the downtime records and sync their productivity logs."""
        records = super().create(vals_list)
        records._sync_productivity()
        return records

    def write(self, vals):
        """Update the downtime and resync productivity when timing or reason fields change."""
        res = super().write(vals)
        if self.env.context.get('htplus_skip_productivity_sync'):
            return res
        if any(k in vals for k in (
            'date_start', 'date_end', 'reason_id', 'workorder_id', 'machine_id', 'employee_id',
        )):
            self._sync_productivity()
        return res
