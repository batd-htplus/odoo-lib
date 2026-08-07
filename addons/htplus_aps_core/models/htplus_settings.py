from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    htplus_aps_objective = fields.Selection([
        ('min_makespan', 'Minimize Makespan'),
        ('min_tardiness', 'Minimize Tardiness'),
        ('min_cost', 'Minimize Cost'),
    ], string='Default Schedule Objective', config_parameter='htplus_aps.objective', default='min_tardiness')
    htplus_aps_capacity_limit_pct = fields.Float(
        string='Default Capacity Limit (%)',
        config_parameter='htplus_aps.capacity_limit_pct', default=90.0)
    htplus_aps_buffer_before = fields.Float(
        string='Default Buffer Before (hours)',
        config_parameter='htplus_aps.buffer_before', default=0.0)
    htplus_aps_buffer_after = fields.Float(
        string='Default Buffer After (hours)',
        config_parameter='htplus_aps.buffer_after', default=0.0)
    htplus_aps_batch_size = fields.Integer(
        string='Default Batch Size',
        config_parameter='htplus_aps.batch_size', default=1)
    htplus_ai_service_url = fields.Char(
        string='AI Service URL',
        config_parameter='htplus_ai.service_url')
