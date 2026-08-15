from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HtplusDowntimeReason(models.Model):
    _name = 'htplus.downtime.reason'
    _description = 'Downtime Reason'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
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
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'machine_id.factory_id'
    _description = 'Downtime'
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', index=True)
    machine_id = fields.Many2one('htplus.machine', string='Machine', index=True, check_company=True)
    reason_id = fields.Many2one('htplus.downtime.reason', required=True, string='Reason')
    type = fields.Selection([
        ('planned', 'Planned'),
        ('unplanned', 'Unplanned'),
    ], default='unplanned')
    date_start = fields.Datetime(required=True, string='Start', index=True)
    date_end = fields.Datetime(string='End', index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True)
    cost = fields.Float()
    @api.depends('machine_id', 'machine_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope downtime by the machine that stopped."""
        return super()._compute_htplus_factory_id()

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

    duration_minutes = fields.Float(
        compute='_compute_duration',
        store=True,
        string='Duration (minutes)',
    )

    def action_end(self):
        """Close an open downtime at the current time.

        An operator opens a downtime the moment a machine stops and has no
        reason to come back to the form afterwards, so the end time was being
        left blank and the duration stayed at zero. Stamping it from a button
        keeps the record honest without asking anyone to type a timestamp.

        Writing date_end also creates and closes the mirrored
        mrp.workcenter.productivity loss log through write(), so Odoo's own
        OEE numbers close out with it.
        """
        open_records = self.filtered(lambda rec: not rec.date_end)
        if not open_records:
            raise UserError(_('This downtime has already been closed.'))
        open_records.write({'date_end': fields.Datetime.now()})
        return True

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
        """Mirror each closed downtime as an mrp.workcenter.productivity loss log.

        Only closed downtimes are mirrored. Odoo 18 allows a single open
        mrp.workcenter.productivity log per work order and user, so creating
        an open loss log while the work order is running would trip the
        'cannot be started twice' check. The log is therefore created when the
        downtime is closed and stays closed.
        """
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
        """Create the downtime records and sync productivity logs for closed ones."""
        records = super().create(vals_list)
        records.filtered(lambda rec: rec.date_end)._sync_productivity()
        return records

    def write(self, vals):
        """Update the downtime and resync productivity when timing or reason fields change.

        Open downtimes are never mirrored, so closing the downtime from
        action_end is what actually creates the loss log.
        """
        res = super().write(vals)
        if self.env.context.get('htplus_skip_productivity_sync'):
            return res
        if any(k in vals for k in (
            'date_start', 'date_end', 'reason_id', 'workorder_id', 'machine_id', 'employee_id',
        )):
            self.filtered(lambda rec: rec.date_end)._sync_productivity()
        return res
