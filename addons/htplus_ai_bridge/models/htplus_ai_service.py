import logging

import requests

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HtplusAiService(models.AbstractModel):
    _name = 'htplus.ai.service'
    _description = 'AI Service Client'

    def _get_config(self):
        config = self.env['htplus.ai.config']._get_active()
        if not config:
            raise ValueError('No active AI service configuration found.')
        return config

    def _call(self, path, payload):
        config = self._get_config()
        url = '%s%s' % (config.url.rstrip('/'), path)
        headers = {'Authorization': 'Bearer %s' % config.api_key, 'Content-Type': 'application/json'}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=config.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.error('AI service call failed: %s', error)
            raise

    def forecast(self, product_ids, horizon_days, history):
        return self._call('/api/v1/forecast', {
            'product_ids': product_ids,
            'horizon_days': horizon_days,
            'history': history,
        })

    def schedule_recommend(self, workorders, constraints, objective='min_tardiness'):
        return self._call('/api/v1/schedule/recommend', {
            'workorders': workorders,
            'constraints': constraints,
            'objective': objective,
        })

    def assignment_recommend(self, workorders, employees, skill_matrix, shifts):
        return self._call('/api/v1/assignment/recommend', {
            'workorders': workorders,
            'employees': employees,
            'skill_matrix': skill_matrix,
            'shifts': shifts,
        })

    def bottleneck_predict(self, period):
        return self._call('/api/v1/bottleneck/predict', {'period': period})

    def delay_predict(self, workorders):
        return self._call('/api/v1/delay/predict', {'workorders': workorders})

    def root_cause(self, workorder_id, history):
        return self._call('/api/v1/root-cause', {
            'workorder_id': workorder_id,
            'history': history,
        })

    def chat(self, session_id, message, context=None):
        return self._call('/api/v1/chat', {
            'session_id': session_id,
            'message': message,
            'context': context or {},
        })

    def poll_job(self, job_id):
        config = self._get_config()
        url = '%s/api/v1/job/%s' % (config.url.rstrip('/'), job_id)
        headers = {'Authorization': 'Bearer %s' % config.api_key}
        try:
            response = requests.get(url, headers=headers, timeout=config.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.error('AI job poll failed: %s', error)
            return {'success': False, 'error': str(error)}
