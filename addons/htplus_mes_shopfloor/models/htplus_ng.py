from odoo import api, fields, models


class HtplusDefect(models.Model):
    _name = 'htplus.defect'
    _description = 'Defect'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    category = fields.Char()
    active = fields.Boolean(default=True)


class HtplusWorkorderNg(models.Model):
    _name = 'htplus.workorder.ng'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'workorder_id.factory_id'
    _description = 'Work Order NG'
    _order = 'date desc'

    workorder_id = fields.Many2one('mrp.workorder', required=True, string='Work Order')
    defect_id = fields.Many2one('htplus.defect', required=True, string='Defect')
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    qty = fields.Float(required=True)
    root_cause = fields.Text(string='Root Cause')
    countermeasure = fields.Text()
    employee_id = fields.Many2one('hr.employee', string='Employee')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    @api.depends('workorder_id', 'workorder_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope an NG record by the work order it was found on."""
        return super()._compute_htplus_factory_id()

