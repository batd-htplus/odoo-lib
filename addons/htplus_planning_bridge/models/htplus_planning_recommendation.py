from odoo import api, fields, models


class HtplusPlanningRecommendation(models.Model):
    _name = 'htplus.planning.recommendation'
    _description = 'Recommendation'
    _inherit = 'htplus.factory.scope.mixin'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True)
    type = fields.Selection([
        ('schedule', 'Schedule'),
        ('assignment', 'Assignment'),
        ('bottleneck', 'Bottleneck'),
        ('delay', 'Delay'),
        ('root_cause', 'Root Cause'),
        ('demand', 'Demand'),
    ], required=True)
    title = fields.Char(required=True)
    summary = fields.Text()
    explanation = fields.Text()
    payload = fields.Json(string='Payload')
    model = fields.Char()
    state = fields.Selection([
        ('new', 'New'),
        ('applied', 'Applied'),
        ('dismissed', 'Dismissed'),
    ], default='new', string='Status')
    source_workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    source_plan_id = fields.Many2one('htplus.production.plan', string='Production Plan', check_company=True)
    user_id = fields.Many2one('res.users', string='Reviewed By')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('source_workorder_id', 'source_workorder_id.factory_id',
                 'source_plan_id', 'source_plan_id.factory_id')
    def _compute_htplus_factory_id(self):
        for record in self:
            record.factory_id = (
                record.source_workorder_id.factory_id
                or record.source_plan_id.factory_id
                or False
            )

    def action_apply(self):
        """Mark the recommendation as applied and record the reviewing user."""
        self.state = 'applied'
        self.user_id = self.env.user

    def action_dismiss(self):
        """Mark the recommendation as dismissed and record the reviewing user."""
        self.state = 'dismissed'
        self.user_id = self.env.user
