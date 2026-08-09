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
    htplus_shift_default_factory = fields.Many2one(
        'htplus.factory', string='Default Factory',
        config_parameter='htplus_shift.default_factory_id')
    htplus_shift_count_per_day = fields.Integer(
        string='Shifts per Day',
        config_parameter='htplus_shift.count_per_day', default=3)
    htplus_shift_std_hours = fields.Float(
        string='Standard Working Hours',
        config_parameter='htplus_shift.std_hours', default=8.0)
    htplus_shift_max_ot = fields.Float(
        string='Max Overtime (hours)',
        config_parameter='htplus_shift.max_ot', default=2.0)
    htplus_shift_ai_auto_assign = fields.Boolean(
        string='Allow AI Auto Assignment',
        config_parameter='htplus_shift.ai_auto_assign', default=False)
    htplus_shift_auto_conflict_check = fields.Boolean(
        string='Auto Conflict Check',
        config_parameter='htplus_shift.auto_conflict_check', default=True)
