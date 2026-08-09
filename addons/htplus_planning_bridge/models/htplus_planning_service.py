import logging
import os
import time

import requests

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HtplusPlanningService(models.AbstractModel):
    _name = 'htplus.planning.service'
    _description = 'AI Service Client'

    def _get_config(self):
        config = self.env['htplus.planning.config']._get_active()
        if not config:
            raise UserError('No active planning engine configuration found.')
        return config

    def _api_key(self, config):
        return (config.api_key or os.environ.get('HTPLUS_PLANNING_API_KEY') or '').strip()

    def _headers(self, config):
        return {
            'Authorization': 'Bearer %s' % self._api_key(config),
            'Content-Type': 'application/json',
        }

    def _call(self, path, payload):
        config = self._get_config()
        url = '%s%s' % (config.url.rstrip('/'), path)
        try:
            response = requests.post(
                url, json=payload, headers=self._headers(config), timeout=config.timeout_sec,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.error('Planning engine call failed: %s', error)
            raise UserError('Planning engine call failed: %s' % error) from error

    def forecast(self, product_ids, horizon_days, history):
        return self._call('/api/v1/forecast', {
            'product_ids': product_ids,
            'horizon_days': horizon_days,
            'history': history,
        })

    def schedule_recommend(self, workorders, constraints, objective='min_tardiness',
                           algorithm='rule_engine'):
        return self._call('/api/v1/schedule/recommend', {
            'workorders': workorders,
            'constraints': constraints,
            'objective': objective,
            'algorithm': algorithm,
        })

    def wait_job(self, job_id, timeout_sec=None, poll_interval=0.5):
        """Poll /api/v1/job/{id} until success/failed or timeout."""
        config = self._get_config()
        timeout = timeout_sec if timeout_sec is not None else config.timeout_sec
        deadline = time.monotonic() + max(timeout, 1)
        url = '%s/api/v1/job/%s' % (config.url.rstrip('/'), job_id)
        headers = {'Authorization': 'Bearer %s' % self._api_key(config)}
        last = {}
        while time.monotonic() < deadline:
            try:
                response = requests.get(url, headers=headers, timeout=min(10, timeout))
                response.raise_for_status()
                last = response.json()
            except requests.exceptions.RequestException as error:
                _logger.error('Planning engine job poll failed: %s', error)
                raise UserError('Planning engine job poll failed: %s' % error) from error
            status = last.get('status')
            if status == 'success':
                return last
            if status == 'failed':
                raise UserError(
                    'Planning engine job failed: %s' % (last.get('error') or 'unknown error')
                )
            time.sleep(poll_interval)
        raise UserError('Planning engine job timed out (job_id=%s).' % job_id)

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
        headers = {'Authorization': 'Bearer %s' % self._api_key(config)}
        try:
            response = requests.get(url, headers=headers, timeout=config.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.error('Planning engine job poll failed: %s', error)
            return {'success': False, 'error': str(error)}
