from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtplusWorkorderActual(models.Model):
    _name = 'htplus.workorder.actual'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'workorder_id.factory_id'
    _description = 'Work Order Actual'
    _rec_name = 'name'
    _order = 'date_start desc'

    name = fields.Char(
        compute='_compute_name',
        store=True,
        string='Actual',
        index=True,
    )

    @api.depends('workorder_id', 'workorder_id.name', 'employee_id', 'employee_id.name', 'date_start')
    def _compute_name(self):
        for rec in self:
            parts = [rec.workorder_id.name or _('No Work Order')]
            if rec.employee_id:
                parts.append(rec.employee_id.name)
            if rec.date_start:
                parts.append(fields.Datetime.to_string(rec.date_start))
            rec.name = ' · '.join(parts)

    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order', index=True)
    date_start = fields.Datetime(required=True, string='Start', index=True)
    date_finished = fields.Datetime(string='Finished')
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True)
    machine_id = fields.Many2one('htplus.machine', string='Machine', index=True)
    qty_done = fields.Float(string='Qty Done')
    qty_good = fields.Float(string='Qty Good')
    qty_ng = fields.Float(string='Qty NG')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('finished', 'Finished'),
    ], default='draft', string='Status', index=True)
    productivity_id = fields.Many2one(
        'mrp.workcenter.productivity',
        string='Odoo Time Log',
        copy=False,
        readonly=True,
        help='Linked mrp.workcenter.productivity row (Fully Productive Time).',
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('workorder_id', 'workorder_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope an actual by the work order it records."""
        return super()._compute_htplus_factory_id()


    @api.constrains('workorder_id', 'state')
    def _check_single_running(self):
        """Ensure a work order has at most one running actual."""
        for rec in self:
            if rec.state == 'running':
                running = self.search([
                    ('workorder_id', '=', rec.workorder_id.id),
                    ('state', '=', 'running'),
                    ('id', '!=', rec.id),
                ])
                if running:
                    raise models.ValidationError(
                        _('A work order can have at most one running actual record.'))

    def _productive_loss(self):
        """Return the fully productive time loss used for the productivity log.

        Returns:
            the mrp.block_reason7 loss recordset.
        """
        return self.env.ref('mrp.block_reason7', raise_if_not_found=False)

    def _sync_productivity(self):
        """Mirror each actual as an mrp.workcenter.productivity fully productive time log."""
        Productivity = self.env['mrp.workcenter.productivity']
        loss = self._productive_loss()
        for rec in self:
            workcenter = rec.workorder_id.workcenter_id
            if not workcenter or not loss:
                continue
            vals = {
                'workcenter_id': workcenter.id,
                'workorder_id': rec.workorder_id.id,
                'loss_id': loss.id,
                'date_start': rec.date_start,
                'date_end': rec.date_finished,
                'company_id': rec.company_id.id,
                'description': _('HTPlus actual #%s', rec.id),
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
        """Create the actuals and sync productivity logs for running records."""
        records = super().create(vals_list)
        records.filtered(lambda r: r.state == 'running')._sync_productivity()
        return records

    def write(self, vals):
        """Update the actual and resync productivity when timing or status fields change."""
        res = super().write(vals)
        if self.env.context.get('htplus_skip_productivity_sync'):
            return res
        if any(k in vals for k in ('date_start', 'date_finished', 'state', 'workorder_id', 'employee_id')):
            self.filtered(lambda r: r.state in ('running', 'finished', 'paused'))._sync_productivity()
        return res

    def action_start(self):
        """Start shop-floor execution for a draft actual, or resume a paused one.

        A resume opens a *new* productivity row: the paused interval was already
        closed by ``action_pause`` and must not be folded into productive time.

        Returns:
            True once the actual is running.
        """
        for rec in self:
            if rec.state == 'finished':
                continue
            running = self.search([
                ('workorder_id', '=', rec.workorder_id.id),
                ('state', '=', 'running'),
                ('id', '!=', rec.id),
            ], limit=1)
            if running:
                raise ValidationError(_(
                    'Work order already has a running actual (%s).'
                ) % running.display_name)
            if rec.state == 'paused':
                if rec.productivity_id:
                    rec.with_context(htplus_skip_productivity_sync=True).write({
                        'productivity_id': False,
                    })
                start = fields.Datetime.now()
            else:
                start = rec.date_start or fields.Datetime.now()
            rec.write({
                'state': 'running',
                'date_start': start,
                'date_finished': False,
            })
        return True

    def action_finish(self):
        """Finish the actual and post the good quantity to the work order."""
        for rec in self:
            if rec.state != 'running':
                raise ValidationError(_('Only a running actual can be finished.'))
            ng = self.env['htplus.workorder.ng'].search([
                ('workorder_id', '=', rec.workorder_id.id),
                ('date', '>=', rec.date_start),
            ])
            if ng and not rec.qty_ng:
                rec.qty_ng = sum(ng.mapped('qty'))
            rec.write({
                'date_finished': fields.Datetime.now(),
                'state': 'finished',
            })
            rec.workorder_id.qty_producing = rec.qty_good

    def action_pause(self):
        """Pause the actual and record the pause time."""
        if any(rec.state != 'running' for rec in self):
            raise ValidationError(_('Only a running actual can be paused.'))
        self.write({
            'state': 'paused',
            'date_finished': fields.Datetime.now(),
        })
