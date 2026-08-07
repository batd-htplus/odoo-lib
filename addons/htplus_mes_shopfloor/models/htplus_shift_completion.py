from odoo import fields, models


class HtplusShiftCompletion(models.Model):
    _name = 'htplus.shift.completion'
    _description = 'Shift Completion'
    _order = 'date desc'

    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    shift_template_id = fields.Many2one('htplus.shift.template', string='Shift Template')
    date = fields.Date(required=True)
    qty_target = fields.Float(string='Qty Target')
    qty_done = fields.Float(string='Qty Done')
    qty_good = fields.Float(string='Qty Good')
    qty_ng = fields.Float(string='Qty NG')
    downtime_minutes = fields.Float(string='Downtime (minutes)')
    remarks = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
