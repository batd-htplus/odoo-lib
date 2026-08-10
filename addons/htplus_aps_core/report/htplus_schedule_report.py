from odoo import api, fields, models


class HtplusScheduleReport(models.Model):
    """Read-only analysis of the schedule, computed by PostgreSQL.

    KPI screens used to be assembled record by record in Python: a search_count
    per figure, a ``filtered`` after a search to narrow it further. That is fine
    against demo data and falls over against a few years of work orders, because
    the cost grows with the number of rows rather than with the number of
    figures on screen.

    This is the shape Odoo uses for its own analysis models (``sale.report``,
    ``mrp.report``): a database view exposed as a model with ``_auto = False``,
    so every dashboard, pivot and graph is one grouped query instead of a loop.

    Read-only by construction - there is no table behind it.
    """

    _name = 'htplus.schedule.report'
    _description = 'Schedule Analysis'
    _auto = False
    _rec_name = 'workorder_id'
    _order = 'date_start desc'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', readonly=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', readonly=True)
    schedule_run_id = fields.Many2one('htplus.schedule.run', string='Schedule Run', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center', readonly=True)
    machine_id = fields.Many2one('htplus.machine', string='Machine', readonly=True)
    line_id = fields.Many2one('htplus.line', string='Line', readonly=True)
    plant_id = fields.Many2one('htplus.plant', string='Plant', readonly=True)
    factory_id = fields.Many2one('htplus.factory', string='Factory', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    date_start = fields.Datetime(string='Start', readonly=True)
    date_finished = fields.Datetime(string='Finish', readonly=True)
    date_day = fields.Date(string='Day', readonly=True)
    date_deadline = fields.Datetime(string='Deadline', readonly=True)

    state = fields.Char(string='WO Status', readonly=True)
    schedule_state = fields.Char(string='Schedule Status', readonly=True)
    locked = fields.Boolean(readonly=True)
    schedule_conflict = fields.Boolean(string='Conflict', readonly=True)

    workorder_count = fields.Integer(string='# Work Orders', readonly=True)
    duration_expected = fields.Float(string='Planned Duration (min)', readonly=True)
    duration_real = fields.Float(string='Actual Duration (min)', readonly=True)
    duration_deviation = fields.Float(string='Duration Deviation (min)', readonly=True)
    qty_production = fields.Float(string='Qty To Produce', readonly=True)
    qty_produced = fields.Float(string='Qty Produced', readonly=True)
    late_count = fields.Integer(string='# Late', readonly=True)

    @property
    def _table_query(self):
        """SQL backing this model.

        Expressed as a property rather than a stored view so the definition
        lives next to the fields it feeds and cannot drift from them.
        """
        return """
            SELECT
                wo.id                                   AS id,
                wo.id                                   AS workorder_id,
                wo.production_id                        AS production_id,
                wo.schedule_run_id                      AS schedule_run_id,
                mo.product_id                           AS product_id,
                wo.workcenter_id                        AS workcenter_id,
                wo.machine_id                           AS machine_id,
                wo.line_id                              AS line_id,
                wc.plant_id                             AS plant_id,
                wo.factory_id                           AS factory_id,
                mo.company_id                           AS company_id,
                wo.date_start                           AS date_start,
                wo.date_finished                        AS date_finished,
                wo.date_start::date                     AS date_day,
                mo.date_deadline                        AS date_deadline,
                wo.state                                AS state,
                wo.schedule_state                       AS schedule_state,
                COALESCE(wo.locked, FALSE)              AS locked,
                COALESCE(wo.schedule_conflict, FALSE)   AS schedule_conflict,
                1                                       AS workorder_count,
                COALESCE(wo.duration_expected, 0.0)     AS duration_expected,
                COALESCE(wo.duration, 0.0)              AS duration_real,
                COALESCE(wo.duration, 0.0)
                    - COALESCE(wo.duration_expected, 0.0) AS duration_deviation,
                COALESCE(mo.product_qty, 0.0)           AS qty_production,
                COALESCE(wo.qty_produced, 0.0)          AS qty_produced,
                CASE
                    WHEN mo.date_deadline IS NOT NULL
                     AND wo.date_finished IS NOT NULL
                     AND wo.date_finished > mo.date_deadline
                    THEN 1 ELSE 0
                END                                     AS late_count
              FROM mrp_workorder wo
              JOIN mrp_production mo ON mo.id = wo.production_id
         LEFT JOIN mrp_workcenter wc ON wc.id = wo.workcenter_id
             WHERE wo.state != 'cancel'
        """

    @api.model
    def _htplus_kpi(self, domain=None):
        """Return headline KPIs for a domain in a single grouped query.

        Args:
            domain: Optional domain narrowing the analysed work orders.

        Returns:
            Dict of aggregate figures.
        """
        groups = self._read_group(
            domain or [],
            aggregates=['workorder_count:sum', 'late_count:sum',
                        'duration_expected:sum', 'duration_real:sum',
                        'qty_production:sum', 'qty_produced:sum'],
        )
        if not groups:
            return dict.fromkeys(
                ('workorders', 'late', 'planned_minutes', 'actual_minutes',
                 'qty_planned', 'qty_produced'), 0.0)
        total, late, planned, actual, qty_plan, qty_done = groups[0]
        return {
            'workorders': total or 0,
            'late': late or 0,
            'planned_minutes': planned or 0.0,
            'actual_minutes': actual or 0.0,
            'qty_planned': qty_plan or 0.0,
            'qty_produced': qty_done or 0.0,
        }
