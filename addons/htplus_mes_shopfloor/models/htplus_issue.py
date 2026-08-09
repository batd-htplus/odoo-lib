from odoo import fields, models


class HtplusMachineStop(models.Model):
    _name = 'htplus.machine.stop'
    _description = 'Machine Stop'

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


class HtplusIssue(models.Model):
    _name = 'htplus.issue'
    _description = 'Issue'
    _order = 'date desc'

    name = fields.Char(required=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
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
    employee_id = fields.Many2one('hr.employee', string='Employee')
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
