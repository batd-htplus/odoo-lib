"""The contract every scheduler returns, whatever engine produced it."""

from datetime import date, datetime


def _plain(value):
    """Reduce a value to something JSON can carry.

    Schedulers naturally hand back ``datetime`` objects and Odoo stores the
    result in a Json column, so the conversion belongs here rather than in every
    caller that happens to persist a result.
    """
    if isinstance(value, datetime):
        return value.isoformat(sep=' ', timespec='seconds')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class HtplusScheduleResult:
    """What a scheduler hands back.

    Not an Odoo model - it never reaches the database. It is the boundary
    between "some engine decided something" and "the run records what was
    decided", and it exists so that boundary is the same shape for the built-in
    rule engine, a CP-SAT solver behind HTTP, and whatever a project plugs in
    later.

    Two fields carry more weight than they look:

    ``unassigned``
        A scheduler is allowed to give up on a work order. What it is not
        allowed to do is give up silently - a planner cannot intervene on a
        gap they were never told about. Every work order that came in must
        come back either assigned or unassigned-with-a-reason.

    ``explanation``
        Required for the same reason: a schedule nobody can question is a
        schedule nobody can trust. It is also what makes an AI suggestion
        reviewable rather than merely obeyed.
    """

    __slots__ = ('assignments', 'unassigned', 'conflicts', 'objective',
                 'algorithm', 'explanation', 'metadata')

    def __init__(self, algorithm, explanation, assignments=None, unassigned=None,
                 conflicts=None, objective=None, metadata=None):
        self.algorithm = algorithm
        self.explanation = explanation
        self.assignments = list(assignments or [])
        self.unassigned = list(unassigned or [])
        self.conflicts = list(conflicts or [])
        self.objective = dict(objective or {})
        self.metadata = dict(metadata or {})

    def add_assignment(self, workorder_id, date_start, date_finished,
                       workcenter_id=None, machine_id=None, line_id=None):
        """Record a placed work order."""
        self.assignments.append({
            'workorder_id': workorder_id,
            'date_start': date_start,
            'date_finished': date_finished,
            'workcenter_id': workcenter_id or False,
            'machine_id': machine_id or False,
            'line_id': line_id or False,
        })

    def add_unassigned(self, workorder_id, reason):
        """Record a work order the scheduler could not place, and why."""
        self.unassigned.append({'workorder_id': workorder_id, 'reason': reason})

    def add_conflict(self, workorder_id, kind, detail=''):
        """Record a work order the scheduler placed but is not happy about."""
        self.conflicts.append({'workorder_id': workorder_id, 'kind': kind, 'detail': detail})

    @property
    def assignment_by_workorder(self):
        """Assignments keyed by work order id, for cheap lookup."""
        return {entry['workorder_id']: entry for entry in self.assignments}

    def validate(self, expected_workorder_ids):
        """Check the result actually answers the question it was asked.

        Args:
            expected_workorder_ids: Ids submitted to the scheduler.

        Returns:
            List of human-readable problems; empty when the result is sound.
        """
        problems = []
        if not self.algorithm:
            problems.append('The result does not say which algorithm produced it.')
        if not self.explanation:
            problems.append('The result carries no explanation.')
        expected = set(expected_workorder_ids)
        answered = {entry['workorder_id'] for entry in self.assignments}
        answered |= {entry['workorder_id'] for entry in self.unassigned}
        missing = expected - answered
        if missing:
            problems.append(
                'Neither scheduled nor explained: %s work order(s) %s'
                % (len(missing), sorted(missing)[:10]))
        stray = answered - expected
        if stray:
            problems.append('Answered about work orders it was not given: %s' % sorted(stray)[:10])
        for entry in self.assignments:
            if not entry.get('date_start') or not entry.get('date_finished'):
                problems.append('Assignment for %s has no dates.' % entry['workorder_id'])
        return problems

    def to_dict(self):
        """Serialisable form, for logging on a run or storing on a job."""
        return _plain({
            'algorithm': self.algorithm,
            'explanation': self.explanation,
            'assignments': self.assignments,
            'unassigned': self.unassigned,
            'conflicts': self.conflicts,
            'objective': self.objective,
            'metadata': self.metadata,
        })

    @classmethod
    def from_dict(cls, data):
        """Rebuild a result from its serialised form."""
        data = data or {}
        return cls(
            algorithm=data.get('algorithm'),
            explanation=data.get('explanation'),
            assignments=data.get('assignments'),
            unassigned=data.get('unassigned'),
            conflicts=data.get('conflicts'),
            objective=data.get('objective'),
            metadata=data.get('metadata'),
        )

    def __repr__(self):
        return '<ScheduleResult %s: %s assigned, %s unassigned, %s conflicts>' % (
            self.algorithm, len(self.assignments), len(self.unassigned), len(self.conflicts))
