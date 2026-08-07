from odoo import http
from odoo.http import request


class HtplusAiWebhook(http.Controller):

    @http.route('/htplus/ai/webhook/<int:forecast_id>', type='json', auth='user', methods=['POST'])
    def forecast_webhook(self, forecast_id, **kwargs):
        forecast = request.env['htplus.ai.forecast'].browse(forecast_id)
        payload = request.jsonrequest or {}
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
