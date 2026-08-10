from odoo import fields, models


class HtplusPlanningRule(models.Model):
    _name = 'htplus.planning.rule'
    _description = 'Planning Rule'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    workcenter_ids = fields.Many2many('mrp.workcenter', string='Work Centers')
    capacity_limit_pct = fields.Float(string='Capacity Limit (%)', default=90.0)
    buffer_before = fields.Float(string='Buffer Before (hours)', default=0.0)
    buffer_after = fields.Float(string='Buffer After (hours)', default=0.0)
    batch_size = fields.Integer(string='Batch Size', default=1)
    max_concurrent = fields.Integer(string='Max Concurrent Operations', default=1)
    objective = fields.Selection([
        ('min_makespan', 'Minimize Makespan'),
        ('min_tardiness', 'Minimize Tardiness'),
        ('min_cost', 'Minimize Cost'),
    ], default='min_tardiness', string='Objective')


class HtplusPriorityRule(models.Model):
    _name = 'htplus.priority.rule'
    _description = 'Priority Rule'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    priority_field = fields.Selection([
        ('date_deadline', 'Deadline'),
        ('customer_priority', 'Customer Priority'),
        ('order_priority', 'Order Priority'),
        ('due_date', 'Due Date'),
    ], required=True)
    weight = fields.Float(string='Weight', default=1.0)


class HtplusCapacityRule(models.Model):
    _name = 'htplus.capacity.rule'
    _description = 'Capacity Rule'

    name = fields.Char(required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', required=True)
    max_units_per_day = fields.Float(string='Max Units per Day')
    max_hours_per_day = fields.Float(string='Max Hours per Day')
    active = fields.Boolean(default=True)


