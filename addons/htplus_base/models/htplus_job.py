import logging
from datetime import timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class HtplusJob(models.Model):
    _name = 'htplus.job'
    _description = 'HTPlus Background Job'
    _table = 'htplus_job'
    _order = 'id desc'

    name = fields.Char(required=True)
    model = fields.Char(string='Model', required=True,
                        help='Technical model name the method is called on.')
    method = fields.Char(string='Method', required=True)
    payload = fields.Json(string='Payload', help='Keyword arguments passed to the method.')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], string='State', default='pending', index=True)
    attempts = fields.Integer(string='Attempts', default=0)
    max_attempts = fields.Integer(string='Max Attempts', default=3)
    scheduled_at = fields.Datetime(string='Scheduled At', index=True)
    started_at = fields.Datetime(string='Started At')
    finished_at = fields.Datetime(string='Finished At')
    result = fields.Json(string='Result')
    error = fields.Text(string='Error')
    idempotency_key = fields.Char(string='Idempotency Key', index=True)
    origin_model = fields.Char(string='Origin Model')
    origin_id = fields.Integer(string='Origin Record')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def init(self):
        """Make the idempotency key unique only among jobs still in flight.

        A plain unique constraint would bind the key forever, so re-running the
        same logical task after it finished would raise instead of enqueuing a
        new job. What must never happen is two *live* jobs sharing a key.
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS htplus_job_idempotency_inflight_uniq
                ON htplus_job (idempotency_key)
             WHERE idempotency_key IS NOT NULL
               AND state IN ('pending', 'running')
        """)

    @api.model
    def _enqueue(self, model, method, payload=None, *, name=None, scheduled_at=None,
                 idempotency_key=None, origin_model=None, origin_id=None, max_attempts=3):
        """Create a background job, reusing an in-flight one with the same key.

        Returns:
            The created (or reused) htplus.job record.
        """
        payload = dict(payload or {})
        if idempotency_key:
            existing = self.search([
                ('idempotency_key', '=', idempotency_key),
                ('state', 'in', ('pending', 'running')),
            ], limit=1)
            if existing:
                return existing
        return self.create({
            'name': name or _('%s.%s', model, method),
            'model': model,
            'method': method,
            'payload': payload,
            'scheduled_at': scheduled_at or fields.Datetime.now(),
            'idempotency_key': idempotency_key,
            'origin_model': origin_model,
            'origin_id': origin_id,
            'max_attempts': max_attempts,
        })

    @api.model
    def _claim_and_run_next(self, limit=20):
        """Cron entry: claim due jobs, then run them one transaction at a time.

        The claim is a single UPDATE guarded by FOR UPDATE SKIP LOCKED, and it is
        committed *before* any job runs. That ordering matters: row locks end at
        the first commit, so claiming with a lock and then committing between
        jobs would leave every not-yet-run job in the batch unclaimed and free
        for another worker to pick up as well.

        Returns:
            Number of jobs executed.
        """
        now = fields.Datetime.now()
        self.env.cr.execute("""
            UPDATE htplus_job
               SET state = 'running', started_at = %(now)s
             WHERE id IN (
                   SELECT id
                     FROM htplus_job
                    WHERE state = 'pending'
                      AND (scheduled_at IS NULL OR scheduled_at <= %(now)s)
                 ORDER BY id
                    LIMIT %(limit)s
                      FOR UPDATE SKIP LOCKED
             )
         RETURNING id
        """, {'now': now, 'limit': limit})
        job_ids = [row[0] for row in self.env.cr.fetchall()]
        if not job_ids:
            return 0
        self.env.cr.commit()
        for job in self.browse(job_ids):
            self._execute_job(job)
            self.env.cr.commit()
        return len(job_ids)

    @api.model
    def _htplus_serialisable(self, value):
        """Return a value safe to store in the Json result column.

        A job is judged by whether its work succeeded, not by whether its return
        value happens to be JSON. Recordsets and other Odoo objects are reduced
        to a short description instead of blowing up the job - and taking the
        completed work down with it on rollback.
        """
        import json
        try:
            json.dumps(value)
            return value
        except TypeError:
            if isinstance(value, models.BaseModel):
                return {'model': value._name, 'ids': value.ids[:100], 'count': len(value)}
            return {'repr': str(value)[:500]}

    def _execute_job(self, job):
        """Execute one claimed job, with retries and exponential backoff.

        The job row is re-read after a rollback so a failed attempt does not
        lose the FOR UPDATE claim state written before the crash.
        """
        try:
            result = getattr(self.env[job.model], job.method)(**(job.payload or {}))
            job.write({
                'state': 'done',
                'finished_at': fields.Datetime.now(),
                'result': self._htplus_serialisable(result),
            })
            _logger.info('Job %s (%s.%s) done', job.id, job.model, job.method)
        except Exception as error:  # noqa: BLE001
            self.env.cr.rollback()
            job = self.browse(job.id)
            attempts = job.attempts + 1
            if attempts >= job.max_attempts:
                job.write({
                    'attempts': attempts,
                    'state': 'failed',
                    'error': str(error),
                    'finished_at': fields.Datetime.now(),
                })
                _logger.error('Job %s (%s.%s) failed after %s attempts: %s',
                              job.id, job.model, job.method, attempts, error)
            else:
                backoff_minutes = 2 ** (attempts - 1)
                job.write({
                    'attempts': attempts,
                    'state': 'pending',
                    'error': str(error),
                    'scheduled_at': fields.Datetime.now() + timedelta(minutes=backoff_minutes),
                })
                _logger.warning('Job %s (%s.%s) attempt %s/%s failed, retrying in %s min: %s',
                                job.id, job.model, job.method, attempts, job.max_attempts,
                                backoff_minutes, error)

    @api.model
    def _retry_failed(self, job_ids=None):
        """Reset failed jobs to pending so the cron can pick them up again."""
        jobs = self.browse(job_ids) if job_ids else self.search([('state', '=', 'failed')])
        jobs.write({'state': 'pending', 'attempts': 0, 'scheduled_at': fields.Datetime.now()})
        return True

    def action_retry(self):
        """Requeue the selected failed jobs."""
        return self._retry_failed(self.ids)

    def action_cancel(self):
        """Cancel pending jobs."""
        self.filtered(lambda j: j.state == 'pending').write({
            'state': 'failed', 'error': _('Cancelled by user'),
            'finished_at': fields.Datetime.now(),
        })
        return True
