from odoo import api, fields, models


class HtplusShiftCompletion(models.Model):
    _name = 'htplus.shift.completion'
    _description = 'Shift Completion'
    _order = 'date desc'

    shift_id = fields.Many2one('htplus.production.shift', required=True,
                               string='Shift')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    date = fields.Date(required=True)
    qty_target = fields.Float(string='Qty Target')
    qty_done = fields.Float(string='Qty Done')
    qty_good = fields.Float(string='Qty Good')
    qty_ng = fields.Float(string='Qty NG')
    downtime_minutes = fields.Float(string='Downtime (minutes)')
    overtime_minutes = fields.Float(string='Overtime (minutes)')
    remarks = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        """Carry the shift's work date and planned quantity onto the completion record."""
        if self.shift_id:
            self.date = self.shift_id.date
            if not self.qty_target:
                self.qty_target = self.shift_id.qty_target

    @api.depends('qty_done', 'qty_target', 'qty_good')
    def _compute_achievement_rate(self):
        """Compute the percentage of the target quantity that was produced."""
        for rec in self:
            rec.achievement_rate = (rec.qty_done / rec.qty_target * 100) if rec.qty_target else 0.0

    achievement_rate = fields.Float(compute='_compute_achievement_rate',
                                    string='Achievement Rate (%)')

    @api.depends('qty_good', 'qty_done')
    def _compute_yield_rate(self):
        """Compute the share of produced quantity that is good."""
        for rec in self:
            rec.yield_rate = (rec.qty_good / rec.qty_done * 100) if rec.qty_done else 0.0

    yield_rate = fields.Float(compute='_compute_yield_rate', string='Yield Rate (%)')
