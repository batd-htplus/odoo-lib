from odoo import api, fields, models, _


class HtplusWorkorderActual(models.Model):
    _name = 'htplus.workorder.actual'
    _description = 'Work Order Actual'
    _order = 'date_start desc'

    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    date_start = fields.Datetime(required=True, string='Start')
    date_finished = fields.Datetime(string='Finished')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    machine_id = fields.Many2one('htplus.machine', string='Machine')
    qty_done = fields.Float(string='Qty Done')
    qty_good = fields.Float(string='Qty Good')
    qty_ng = fields.Float(string='Qty NG')
    state = fields.Selection([
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('finished', 'Finished'),
    ], default='running', string='Status')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.constrains('workorder_id', 'state')
    def _check_single_running(self):
        for rec in self:
            if rec.state == 'running':
                running = self.search([
                    ('workorder_id', '=', rec.workorder_id.id),
                    ('state', '=', 'running'),
                    ('id', '!=', rec.id),
                ])
                if running:
                    raise models.ValidationError(_('A work order can have at most one running actual record.'))

    def action_finish(self):
        for rec in self:
            rec.date_finished = fields.Datetime.now()
            rec.state = 'finished'
            rec.workorder_id.write({
                'qty_producing': rec.qty_good,
                'date_finished': rec.date_finished,
            })

    def action_pause(self):
        self.state = 'paused'
