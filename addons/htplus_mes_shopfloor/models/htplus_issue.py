from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HtplusMachineStop(models.Model):
    _name = 'htplus.machine.stop'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'machine_id.factory_id'
    _description = 'Machine Stop'
    _order = 'date_start desc, id desc'

    machine_id = fields.Many2one('htplus.machine', required=True, string='Machine', index=True)
    date_start = fields.Datetime(required=True, string='Start', index=True)
    date_end = fields.Datetime(string='End')
    reason_id = fields.Many2one('htplus.downtime.reason', string='Reason')
    type = fields.Selection([
        ('planned', 'Planned'),
        ('unplanned', 'Unplanned'),
    ], default='unplanned')
    duration_minutes = fields.Float(string='Duration (minutes)')
    cost = fields.Float()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    @api.depends('machine_id', 'machine_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a machine stop by the machine that stopped."""
        return super()._compute_htplus_factory_id()

    def action_end(self):
        """Close an open machine stop and fill in how long it lasted.

        duration_minutes stays a plain editable field here rather than a
        computed one, because records already in the database carry values
        typed in by hand and a stored compute would silently overwrite them.
        The button only fills the duration it just measured itself.
        """
        open_records = self.filtered(lambda rec: not rec.date_end)
        if not open_records:
            raise UserError(_('This machine stop has already been closed.'))
        now = fields.Datetime.now()
        for rec in open_records:
            rec.write({
                'date_end': now,
                'duration_minutes': (now - rec.date_start).total_seconds() / 60.0,
            })
        return True



class HtplusIssue(models.Model):
    _name = 'htplus.issue'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'workorder_id.factory_id'
    _description = 'Issue'
    _order = 'date desc'

    name = fields.Char(required=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', index=True)
    type = fields.Selection([
        ('material', 'Material'),
        ('machine', 'Machine'),
        ('manpower', 'Manpower'),
        ('quality', 'Quality'),
        ('safety', 'Safety'),
        ('other', 'Other'),
    ], default='other')
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium')
    state = fields.Selection([
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], default='open', string='Status', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    root_cause = fields.Text(string='Root Cause')
    countermeasure = fields.Text()
    @api.depends('workorder_id', 'workorder_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope an issue by the work order it was raised against."""
        return super()._compute_htplus_factory_id()

    employee_id = fields.Many2one('hr.employee', string='Employee', index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def action_open(self):
        """Reopen the issue by setting its status to open."""
        self.state = 'open'

    def action_in_progress(self):
        """Move the issue to in progress."""
        self.state = 'in_progress'

    def action_resolve(self):
        """Resolve the issue."""
        self.state = 'resolved'

    def action_close(self):
        """Close the issue."""
        self.state = 'closed'
