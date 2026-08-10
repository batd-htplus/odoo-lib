import hashlib
import json
import logging
import os
import random
import time

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HtplusPlanningService(models.AbstractModel):
    _name = 'htplus.planning.service'
    _description = 'AI Service Client'

    def _get_config(self):
        """Return the active planning engine configuration, raising if none exists."""
        config = self.env['htplus.planning.config']._get_active()
        if not config:
            raise UserError('No active planning engine configuration found.')
        return config

    def _api_key(self, config):
        """Return the API key from config or the environment, falling back to empty."""
        return (config.api_key or os.environ.get('HTPLUS_PLANNING_API_KEY') or '').strip()

    def _headers(self, config):
        """Build the JSON authorization headers for planning engine requests."""
        return {
            'Authorization': 'Bearer %s' % self._api_key(config),
            'Content-Type': 'application/json',
        }

    def _idempotency_key(self, path, payload):
        """Derive a deterministic idempotency key from the endpoint and payload.

        Re-submitting the same payload reuses the engine job instead of
        recomputing it, protecting against double-submit after a timeout.
        """
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(',', ':'))
        return hashlib.sha256(('%s|%s' % (path, canonical)).encode('utf-8')).hexdigest()

    @staticmethod
    def _retryable(error):
        """Return True when the error is transient and safe to retry."""
        if isinstance(error, requests.exceptions.RequestException):
            response = getattr(error, 'response', None)
            if response is not None:
                return response.status_code in (429, 500, 502, 503, 504)
            return True
        return False

    def _degraded_error(self, config):
        return UserError(
            'Planning engine is in degraded mode (circuit breaker open since %s). '
            'Requests are paused; retry later or reset the circuit on the '
            'engine configuration.' % fields.Datetime.to_string(config.circuit_open_since)
        )

    def _log(self, config, **kwargs):
        """Delegate a request-log write to the log model."""
        return self.env['htplus.planning.request.log']._log(config, **kwargs)

    def _call(self, path, payload):
        """POST a payload to the planning engine endpoint with resilience.

        Retries transient failures with exponential backoff, honours a
        per-config circuit breaker, sends an idempotency key, and records every
        call in the request log. When the circuit is open the request is refused
        immediately (degraded mode) instead of blocking the UI.

        Args:
            path: API endpoint path relative to the service URL.
            payload: Dict of parameters sent to the planning engine.

        Returns:
            The JSON response dict from the planning engine.
        """
        config = self._get_config()
        if not config._circuit_allows():
            self._log(config, endpoint=path, method='post', status='skipped',
                        request_payload=payload, error='Circuit breaker open')
            raise self._degraded_error(config)
        url = '%s%s' % (config.url.rstrip('/'), path)
        headers = self._headers(config)
        idempotency_key = self._idempotency_key(path, payload)
        headers['X-Idempotency-Key'] = idempotency_key
        attempt = 0
        last_error = None
        while True:
            started = time.monotonic()
            try:
                response = requests.post(
                    url, json=payload, headers=headers, timeout=config.timeout_sec,
                )
                response.raise_for_status()
                result = response.json()
                config._circuit_record_success()
                self._log(config, endpoint=path, method='post', status='success',
                            status_code=response.status_code, retries=attempt,
                            idempotency_key=idempotency_key, request_payload=payload,
                            response=result,
                            response_time_ms=int((time.monotonic() - started) * 1000))
                return result
            except requests.exceptions.RequestException as error:
                last_error = error
                response = getattr(error, 'response', None)
                status_code = response.status_code if response is not None else None
                if not self._retryable(error) or attempt >= config.retry_max:
                    break
                attempt += 1
                _logger.warning(
                    'Planning engine call failed (attempt %s/%s), retrying: %s',
                    attempt, config.retry_max, error,
                )
                backoff = config.retry_backoff * (2 ** (attempt - 1))
                time.sleep(backoff * (0.5 + random.random()))
        if self._retryable(last_error):
            config._circuit_record_failure()
        _logger.error('Planning engine call failed: %s', last_error)
        self._log(config, endpoint=path, method='post', status='failed',
                    status_code=status_code, retries=attempt,
                    idempotency_key=idempotency_key, request_payload=payload,
                    error=str(last_error),
                    response_time_ms=int((time.monotonic() - started) * 1000))
        raise UserError('Planning engine call failed: %s' % last_error) from last_error

    def forecast(self, product_ids, horizon_days, history):
        """Submit a demand forecast request to the planning engine."""
        return self._call('/api/v1/forecast', {
            'product_ids': product_ids,
            'horizon_days': horizon_days,
            'history': history,
        })

    def schedule_recommend(self, workorders, constraints, objective='min_tardiness',
                           algorithm='rule_engine'):
        """Submit a schedule recommendation request to the planning engine."""
        return self._call('/api/v1/schedule/recommend', {
            'workorders': workorders,
            'constraints': constraints,
            'objective': objective,
            'algorithm': algorithm,
        })

    def wait_job(self, job_id, timeout_sec=None, poll_interval=0.5):
        """Poll the planning engine job endpoint until it succeeds, fails, or times out."""
        config = self._get_config()
        timeout = timeout_sec if timeout_sec is not None else config.timeout_sec
        deadline = time.monotonic() + max(timeout, 1)
        url = '%s/api/v1/job/%s' % (config.url.rstrip('/'), job_id)
        headers = self._headers(config)
        last = {}
        while time.monotonic() < deadline:
            started = time.monotonic()
            try:
                response = requests.get(url, headers=headers, timeout=min(10, timeout))
                response.raise_for_status()
                last = response.json()
                config._circuit_record_success()
                self._log(config, endpoint=url, method='get', status='success',
                            status_code=response.status_code, idempotency_key=job_id,
                            response=last,
                            response_time_ms=int((time.monotonic() - started) * 1000))
            except requests.exceptions.RequestException as error:
                _logger.error('Planning engine job poll failed: %s', error)
                if self._retryable(error):
                    config._circuit_record_failure()
                self._log(config, endpoint=url, method='get', status='failed',
                            idempotency_key=job_id, error=str(error),
                            response_time_ms=int((time.monotonic() - started) * 1000))
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
        """Submit an assignment recommendation request to the planning engine."""
        return self._call('/api/v1/assignment/recommend', {
            'workorders': workorders,
            'employees': employees,
            'skill_matrix': skill_matrix,
            'shifts': shifts,
        })

    def bottleneck_predict(self, period):
        """Ask the planning engine to predict bottlenecks for the given period."""
        return self._call('/api/v1/bottleneck/predict', {'period': period})

    def delay_predict(self, workorders):
        """Ask the planning engine to predict delays for the given work orders."""
        return self._call('/api/v1/delay/predict', {'workorders': workorders})

    def root_cause(self, workorder_id, history):
        """Ask the planning engine to analyse the root cause of a work order issue."""
        return self._call('/api/v1/root-cause', {
            'workorder_id': workorder_id,
            'history': history,
        })

    def chat(self, session_id, message, context=None):
        """Send a chat message to the planning assistant for the given session."""
        return self._call('/api/v1/chat', {
            'session_id': session_id,
            'message': message,
            'context': context or {},
        })

    def poll_job(self, job_id):
        """Fetch the current status of a planning engine job without waiting.

        Returns a dict that is always safe to read; never raises.
        """
        config = self._get_config()
        url = '%s/api/v1/job/%s' % (config.url.rstrip('/'), job_id)
        headers = self._headers(config)
        started = time.monotonic()
        try:
            response = requests.get(url, headers=headers, timeout=config.timeout_sec)
            response.raise_for_status()
            result = response.json()
            config._circuit_record_success()
            self._log(config, endpoint=url, method='get', status='success',
                        status_code=response.status_code, idempotency_key=job_id,
                        response=result,
                        response_time_ms=int((time.monotonic() - started) * 1000))
            return result
        except requests.exceptions.RequestException as error:
            _logger.error('Planning engine job poll failed: %s', error)
            if self._retryable(error):
                config._circuit_record_failure()
            self._log(config, endpoint=url, method='get', status='failed',
                        idempotency_key=job_id, error=str(error),
                        response_time_ms=int((time.monotonic() - started) * 1000))
            return {'success': False, 'error': str(error)}
