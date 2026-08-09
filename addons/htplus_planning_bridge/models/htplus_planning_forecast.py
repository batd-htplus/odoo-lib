from odoo import fields, models, api, _


class HtplusPlanningForecast(models.Model):
    _name = 'htplus.planning.forecast'
    _description = 'Demand Forecast'

    name = fields.Char(required=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('applied', 'Applied'),
    ], default='draft', string='Status')
    config_id = fields.Many2one('htplus.planning.config', string='Engine Configuration')
    model = fields.Char()
    horizon_days = fields.Integer(string='Horizon (days)', default=90)
    date_start = fields.Date(required=True)
    date_end = fields.Date()
    product_ids = fields.Many2many('product.product', string='Products')
    line_ids = fields.One2many('htplus.planning.forecast.line', 'forecast_id', string='Lines')
    job_id = fields.Char(string='Job ID')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model
    def poll_pending_jobs(self):
        """Poll the planning engine for finished jobs and store completed forecast lines."""
        pending = self.search([('state', '=', 'draft'), ('job_id', '!=', False)])
        for forecast in pending:
            result = self.env['htplus.planning.service'].poll_job(forecast.job_id)
            if result.get('success') and result.get('data', {}).get('lines'):
                lines = [(0, 0, {
                    'product_id': item['product_id'],
                    'date': item['date'],
                    'qty': item['qty'],
                    'confidence': item.get('confidence', 0.0),
                    'model': item.get('model', ''),
                }) for item in result['data']['lines']]
                forecast.line_ids = lines
                forecast.state = 'computed'
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """Assign a sequence name to new forecasts that still hold the default label."""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('htplus.planning.forecast') or _('New')
        return super().create(vals_list)

    def action_run(self):
        """Submit a demand forecast to the planning engine and store the resulting lines."""
        self.ensure_one()
        if not self.config_id:
            self.config_id = self.env['htplus.planning.config']._get_active()
        history = [{
            'date': line.date.isoformat(),
            'product_id': line.product_id.id,
            'qty': line.qty,
        } for line in self.env['htplus.demand.plan.line'].search([], limit=1000)]
        result = self.env['htplus.planning.service'].forecast(
            self.product_ids.ids, self.horizon_days, history)
        if result.get('forecast_id'):
            self.job_id = result['forecast_id']
            return True
        lines = [(0, 0, {
            'product_id': item['product_id'],
            'date': item['date'],
            'qty': item['qty'],
            'confidence': item.get('confidence', 0.0),
            'model': result.get('model', self.model),
        }) for item in result.get('lines', [])]
        self.line_ids = lines
        self.state = 'computed'
        return True

    def action_apply(self):
        """Materialise the forecast lines into a demand plan and mark the forecast applied."""
        for forecast in self:
            plan = self.env['htplus.demand.plan'].create({
                'date_start': self.date_start,
                'date_end': self.date_end,
                'source': 'ai',
                'planning_forecast_id': forecast.id,
            })
            for line in forecast.line_ids:
                plan.line_ids = [(0, 0, {
                    'product_id': line.product_id.id,
                    'date': line.date,
                    'qty': line.qty,
                    'uom_id': line.product_id.uom_id.id,
                    'forecast_confidence': line.confidence,
                })]
            forecast.state = 'applied'


class HtplusPlanningForecastLine(models.Model):
    _name = 'htplus.planning.forecast.line'
    _description = 'Forecast Line'

    forecast_id = fields.Many2one('htplus.planning.forecast', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    date = fields.Date(required=True)
    qty = fields.Float(required=True)
    confidence = fields.Float(string='Confidence')
    model = fields.Char()
