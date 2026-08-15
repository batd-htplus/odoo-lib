from odoo import _, api, fields, models
from odoo.exceptions import UserError

# How many work orders one Apply transaction handles. Batch identity is a count
# of records, never a time window: five thousand work orders can share a single
# hour, and one machine can hold two in a week.
HTPLUS_APPLY_BATCH_SIZE = 200


class HtplusScheduleLine(models.Model):
    """A schedule run's proposal for one work order.

    The intent, kept apart from the execution. ``mrp.workorder`` says what the
    shop floor is actually doing; this says what a given version of a given run
    *wants* it to do. Keeping the two separate is what makes a schedule
    versionable, re-appliable and revertible - none of which is possible when
    the solver writes straight onto the work order.
    """

    _name = 'htplus.schedule.line'
    _description = 'Schedule Run Proposal Line'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'schedule_run_id.factory_id'
    _order = 'schedule_run_id, sequence, id'

    schedule_run_id = fields.Many2one(
        'htplus.schedule.run', required=True, ondelete='cascade', index=True)
    version = fields.Integer(
        string='Run Version', required=True, default=1,
        help='Version of the run this proposal belongs to. Older versions are kept '
             'so a schedule can be reverted to what it looked like before.')
    sequence = fields.Integer(default=10)
    workorder_id = fields.Many2one(
        'mrp.workorder', required=True, ondelete='cascade', index=True)
    date_start = fields.Datetime(string='Proposed Start')
    date_finished = fields.Datetime(string='Proposed Finish')
    machine_id = fields.Many2one('htplus.machine', string='Proposed Machine')
    line_id = fields.Many2one('htplus.line', string='Proposed Line')
    applied = fields.Boolean(
        default=False, index=True,
        help='Set once this proposal has been written onto the work order.')

    _sql_constraints = [
        ('run_version_workorder_uniq',
         'unique(schedule_run_id, version, workorder_id)',
         'A run version may only hold one proposal per work order.'),
    ]

    @api.depends('schedule_run_id', 'schedule_run_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a proposal line by the run it belongs to."""
        return super()._compute_htplus_factory_id()

    def _htplus_workorder_vals(self):
        """Return the values this proposal writes onto its work order."""
        self.ensure_one()
        return {
            'date_start': self.date_start,
            'date_finished': self.date_finished,
            'machine_id': self.machine_id.id or False,
            'line_id': self.line_id.id or False,
            'schedule_state': 'confirmed',
            'schedule_run_id': self.schedule_run_id.id,
        }


class HtplusApplyBatch(models.Model):
    """One transaction's worth of an Apply.

    Applying a whole run in a single transaction is how a scheduler dies in
    production: it holds write locks on ``mrp_workorder`` for minutes and then
    gets killed by ``limit_time_real``, leaving nothing applied and no record of
    how far it got. Batches make the operation resumable - a failure costs one
    batch, not the run - and give each unit a stable identity to be idempotent
    against.
    """

    _name = 'htplus.apply.batch'
    _inherit = ['htplus.factory.scope.mixin']
    _htplus_factory_path = 'schedule_run_id.factory_id'
    _description = 'Schedule Apply Batch'
    _order = 'schedule_run_id, sequence'

    schedule_run_id = fields.Many2one(
        'htplus.schedule.run', required=True, ondelete='cascade', index=True)
    version = fields.Integer(string='Run Version', required=True)
    sequence = fields.Integer(required=True, help='Order this batch is applied in.')
    line_ids = fields.Many2many('htplus.schedule.line', string='Proposal Lines')
    line_count = fields.Integer(compute='_compute_line_count', store=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], default='pending', index=True)
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    error = fields.Text()

    _sql_constraints = [
        ('run_version_sequence_uniq',
         'unique(schedule_run_id, version, sequence)',
         'Batch sequence must be unique within a run version.'),
    ]

    @api.depends('line_ids')
    def _compute_line_count(self):
        """Keep the line count queryable without loading the lines."""
        for batch in self:
            batch.line_count = len(batch.line_ids)

    @api.depends('schedule_run_id', 'schedule_run_id.factory_id')
    def _compute_htplus_factory_id(self):
        """Scope a batch by the schedule run it belongs to."""
        return super()._compute_htplus_factory_id()

    @property
    def htplus_idempotency_key(self):
        """Stable key identifying this exact unit of work."""
        self.ensure_one()
        return 'apply:%s:%s:%s' % (self.schedule_run_id.id, self.version, self.sequence)

    def _htplus_run(self):
        """Write this batch's proposals onto their work orders.

        Idempotent by construction: a batch already marked done returns without
        touching anything, so a retried job, a double click or a resumed run all
        converge on the same result.
        """
        self.ensure_one()
        if self.state == 'done':
            return True
        self.write({'state': 'pending', 'started_at': fields.Datetime.now(), 'error': False})
        try:
            lines = self.line_ids.filtered(lambda line: line.workorder_id.state != 'cancel')
            for line in lines:
                workorder = line.workorder_id
                workorder.with_context(htplus_force_locked_write=True).write(
                    line._htplus_workorder_vals())
            lines.write({'applied': True})
            self.write({'state': 'done', 'finished_at': fields.Datetime.now()})
        except Exception as error:  # noqa: BLE001 - recorded, not swallowed
            self.write({
                'state': 'failed',
                'finished_at': fields.Datetime.now(),
                'error': str(error),
            })
            raise
        return True


class HtplusScheduleRun(models.Model):
    """Apply: the controlled hand-off from planning intent to execution."""

    _inherit = 'htplus.schedule.run'

    line_ids = fields.One2many(
        'htplus.schedule.line', 'schedule_run_id', string='Proposals')
    apply_batch_ids = fields.One2many(
        'htplus.apply.batch', 'schedule_run_id', string='Apply Batches')
    apply_state = fields.Selection([
        ('none', 'Not Applied'),
        ('applying', 'Applying'),
        ('applied', 'Applied'),
        ('failed', 'Failed'),
    ], default='none', string='Apply Status', index=True, tracking=True)
    apply_progress = fields.Char(compute='_compute_apply_progress', string='Applied')

    @api.depends('apply_batch_ids.state')
    def _compute_apply_progress(self):
        """Show how far an Apply got, so a stuck run is visible without digging."""
        for run in self:
            batches = run.apply_batch_ids.filtered(lambda b: b.version == run.version)
            done = len(batches.filtered(lambda b: b.state == 'done'))
            run.apply_progress = '%s / %s' % (done, len(batches)) if batches else ''

    def _htplus_snapshot_proposals(self):
        """Record the current work order schedule as this version's proposal.

        Called when a run is calculated. Until the solver writes proposals
        directly, this captures what it produced so Apply, revert and version
        comparison all have something concrete to work from.
        """
        Line = self.env['htplus.schedule.line']
        for run in self:
            existing = {line.workorder_id.id: line for line in run.line_ids
                        if line.version == run.version}
            sequence = 0
            create_vals = []
            for workorder in run.workorder_ids.sorted(lambda w: (w.date_start or fields.Datetime.now(), w.id)):
                if not workorder.date_start:
                    continue
                sequence += 10
                vals = {
                    'sequence': sequence,
                    'date_start': workorder.date_start,
                    'date_finished': workorder.date_finished,
                    'machine_id': workorder.machine_id.id or False,
                    'line_id': workorder.line_id.id or False,
                }
                line = existing.get(workorder.id)
                if line:
                    line.write(vals)
                else:
                    create_vals.append(dict(
                        vals,
                        schedule_run_id=run.id,
                        version=run.version,
                        workorder_id=workorder.id,
                    ))
            if create_vals:
                Line.create(create_vals)
        return True

    def _htplus_build_apply_batches(self):
        """Split this version's proposals into fixed-size batches.

        Returns:
            The batches for the current version, creating them if needed.
        """
        self.ensure_one()
        Batch = self.env['htplus.apply.batch']
        existing = self.apply_batch_ids.filtered(lambda b: b.version == self.version)
        if existing:
            return existing
        lines = self.line_ids.filtered(lambda l: l.version == self.version).sorted('sequence')
        if not lines:
            raise UserError(_(
                'Nothing to apply on %s: the run has no proposals. Calculate it first.'
            ) % self.display_name)
        batches = Batch.browse()
        for index in range(0, len(lines), HTPLUS_APPLY_BATCH_SIZE):
            chunk = lines[index:index + HTPLUS_APPLY_BATCH_SIZE]
            batches |= Batch.create({
                'schedule_run_id': self.id,
                'version': self.version,
                'sequence': index // HTPLUS_APPLY_BATCH_SIZE + 1,
                'line_ids': [(6, 0, chunk.ids)],
            })
        return batches

    def action_apply(self):
        """Hand this run's proposals to the shop floor, in the background.

        Only a confirmed run may be applied - Apply is the point of no return,
        so it sits behind the same approval gate as every other transition.
        """
        self._htplus_require_role('manager')
        for run in self:
            if run.state not in ('confirmed', 'locked'):
                raise UserError(_(
                    'Only a confirmed schedule can be applied. %s is "%s".'
                ) % (run.display_name, run.state))
            if run.apply_state == 'applying':
                raise UserError(_(
                    'An Apply is already running on %s. Wait for it to finish or '
                    'reset the run first.'
                ) % run.display_name)
            run._htplus_build_apply_batches()
            run.apply_state = 'applying'
            self.env['htplus.job']._enqueue(
                'htplus.schedule.run', '_htplus_apply_pending_batches',
                {'run_id': run.id},
                name=_('Apply %s (v%s)', run.display_name, run.version),
                idempotency_key='apply-run:%s:%s' % (run.id, run.version),
                origin_model='htplus.schedule.run', origin_id=run.id,
            )
        return True

    @api.model
    def _htplus_apply_pending_batches(self, run_id):
        """Job entry point: apply every batch of a run that is not done yet.

        Each batch commits on its own, so an interrupted Apply resumes at the
        first batch that has not finished instead of redoing the work.

        Returns:
            Dict summarising how many batches were applied and how many failed.
        """
        run = self.browse(run_id)
        if not run or run.apply_state != 'applying':
            return {'run_id': run_id, 'applied': 0, 'failed': 0, 'remaining': 0}
        applied = failed = 0
        try:
            for batch in run.apply_batch_ids.filtered(
                    lambda b: b.version == run.version and b.state != 'done'
            ).sorted('sequence'):
                if self.browse(run_id).state not in ('confirmed', 'locked'):
                    break
                try:
                    batch._htplus_run()
                    self.env.cr.commit()
                    applied += 1
                except Exception:  # noqa: BLE001 - the batch recorded its own error
                    self.env.cr.rollback()
                    # Re-read after rollback: the failure state was rolled back too.
                    self.browse(run_id).apply_batch_ids.filtered(
                        lambda b: b.id == batch.id
                    ).write({'state': 'failed', 'finished_at': fields.Datetime.now()})
                    self.env.cr.commit()
                    failed += 1
                    break
        except Exception:  # noqa: BLE001 - never leave the run 'applying' forever
            self.env.cr.rollback()
            self.browse(run_id).write({'apply_state': 'failed'})
            self.env.cr.commit()
            raise
        run = self.browse(run_id)
        if run.state not in ('confirmed', 'locked'):
            run.write({'apply_state': 'none'})
        else:
            remaining = run.apply_batch_ids.filtered(
                lambda b: b.version == run.version and b.state != 'done')
            run.apply_state = 'failed' if (failed or remaining) else 'applied'
        self.env.cr.commit()
        return {'run_id': run_id, 'applied': applied, 'failed': failed,
                'remaining': len(remaining)}

    def action_retry_apply(self):
        """Requeue the batches of a failed Apply."""
        self._htplus_require_role('manager')
        for run in self:
            run.apply_batch_ids.filtered(
                lambda b: b.version == run.version and b.state == 'failed'
            ).write({'state': 'pending', 'error': False})
        return self.action_apply()
