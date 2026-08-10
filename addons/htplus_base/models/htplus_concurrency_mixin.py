from odoo import fields, models, _
from odoo.exceptions import UserError


class HtplusConcurrencyMixin(models.AbstractModel):
    """Optimistic locking for records edited from long-lived client views.

    PostgreSQL serialisation plus Odoo's RPC-level retry already cover ordinary
    forms. They do not cover a client that holds stale state on screen for
    minutes - a Gantt board being dragged is the case this exists for. The
    client sends back the ``write_date`` it last saw and the write is refused if
    the record moved underneath it.

    This only detects *stale writes*. It does not detect *business conflicts*,
    where two parties both write fresh data that happens to overlap - that needs
    an interval check at the database level, not a version token.

    Usage::

        class MrpWorkorder(models.Model):
            _inherit = ['mrp.workorder', 'htplus.concurrency.mixin']
            _htplus_concurrency_fields = ('date_start', 'date_finished')

    Context keys (names are part of the client contract - do not rename):
        htplus_expected_write_date: ISO datetime for a single-record write.
        htplus_expected_write_dates: {record_id: ISO datetime} for a batch.
    """

    _name = 'htplus.concurrency.mixin'
    _description = 'HTPlus Optimistic Locking'

    # Writing any of these fields triggers the staleness check.
    _htplus_concurrency_fields = ()

    def _htplus_expected_write_dates(self):
        """Return the {record_id: expected write_date string} sent by the client.

        Returns:
            Dict keyed by record id. Empty when the client sent nothing.
        """
        expected = dict(self.env.context.get('htplus_expected_write_dates') or {})
        single = self.env.context.get('htplus_expected_write_date')
        if single and len(self) == 1:
            expected.setdefault(self.id, single)
        return {int(key): value for key, value in expected.items() if value}

    def _htplus_check_optimistic_lock(self):
        """Refuse the write when a record changed since the client last read it.

        Raises:
            UserError: A record's write_date no longer matches what was expected.
        """
        expected = self._htplus_expected_write_dates()
        if not expected:
            return
        conflicts = self.browse()
        for record in self:
            want = expected.get(record.id)
            if not want or not record.write_date:
                continue
            want_dt = fields.Datetime.to_datetime(want)
            if not want_dt:
                continue
            if record.write_date.replace(microsecond=0) != want_dt.replace(microsecond=0):
                conflicts |= record
        if conflicts:
            raise UserError(_(
                'These records were changed by someone else while you were '
                'editing: %(names)s. Reload before saving.',
                names=', '.join(conflicts[:5].mapped('display_name')),
            ))

    def write(self, vals):
        """Check the optimistic lock before writing tracked fields."""
        watched = set(self._htplus_concurrency_fields)
        client_sent_token = (
            self.env.context.get('htplus_expected_write_date')
            or self.env.context.get('htplus_expected_write_dates')
        )
        if client_sent_token or (watched and watched.intersection(vals)):
            self._htplus_check_optimistic_lock()
        return super().write(vals)
