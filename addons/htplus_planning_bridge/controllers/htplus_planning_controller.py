from odoo import http
from odoo.http import request

from odoo.exceptions import AccessDenied


class HtplusPlanningWebhook(http.Controller):

    def _htplus_authorize_webhook(self, config):
        """Reject engine callbacks that do not carry the configured API key.

        The planning engine is the only expected caller of the forecast
        callback. Requiring its API key here stops any authenticated web user
        from overwriting a forecast or flipping it to computed.
        """
        token = request.httprequest.headers.get('Authorization', '')
        if token.startswith('Bearer '):
            token = token[len('Bearer '):]
        if not config.api_key or token != config.api_key:
            raise AccessDenied('Invalid or missing webhook API key.')

    @http.route('/htplus_planning/webhook/forecast/<int:forecast_id>', type='json', auth='user', methods=['POST'])
    def forecast_webhook(self, forecast_id, **kwargs):
        """Store the forecast payload sent by the planning engine on the given forecast."""
        Config = request.env['htplus.planning.config']
        forecast = request.env['htplus.planning.forecast'].sudo().browse(forecast_id)
        config = (forecast.config_id or Config._get_active()).sudo()
        self._htplus_authorize_webhook(config)
        if not forecast:
            return {'success': False, 'error': 'forecast not found'}
        payload = request.get_json_data() or {}
        lines = [(0, 0, {
            'product_id': item['product_id'],
            'date': item['date'],
            'qty': item['qty'],
            'confidence': item.get('confidence', 0.0),
            'model': item.get('model', ''),
        }) for item in payload.get('lines', [])]
        if lines:
            forecast.line_ids = lines
        forecast.state = 'computed'
        return {'success': True}
