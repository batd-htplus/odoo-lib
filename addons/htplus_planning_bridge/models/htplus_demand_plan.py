from odoo import fields, models


class HtplusDemandPlan(models.Model):
    """Link a demand plan back to the forecast that produced it.

    Lives in the bridge: APS owns demand planning and must keep working when no
    planning engine is deployed, so it cannot reference the forecast model.
    """

    _inherit = 'htplus.demand.plan'

    planning_forecast_id = fields.Many2one(
        'htplus.planning.forecast', string='Demand Forecast')
