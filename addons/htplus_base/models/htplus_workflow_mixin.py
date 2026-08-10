from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError


class HtplusWorkflowMixin(models.AbstractModel):
    """Declarative state transitions for HTPlus documents.

    A model using this mixin keeps owning its own ``state`` Selection field (the
    labels differ per document) and declares the legal moves between states in
    ``_htplus_transitions``. The mixin owns the guard rails that every document
    needs and that are easy to forget when each action is hand-written: the
    source state check, the role check, and the hook points around the change.

    Declaration::

        _htplus_transitions = {
            'confirm': {'from': ('draft',),     'to': 'confirmed', 'role': 'planner'},
            'approve': {'from': ('confirmed',), 'to': 'approved',  'role': 'manager'},
        }

    Roles are indirections, not a second security system: they resolve to real
    Odoo groups through ``_htplus_group_map``, which the domain layer fills by
    extending this mixin. A role with no mapping is a configuration error and is
    treated as "denied", never as "allowed".
    """

    _name = 'htplus.workflow.mixin'
    _description = 'HTPlus Declarative Workflow'

    # {code: {'from': tuple_of_states, 'to': state, 'role': role_name or None}}
    _htplus_transitions = {}
    # {role_name: security group XML id} - filled by the domain layer.
    _htplus_group_map = {}

    htplus_allowed_transitions = fields.Char(
        compute='_compute_htplus_allowed_transitions',
        string='Allowed Transitions',
        help='Transition codes currently available to this user, wrapped in commas '
             '(",confirm,approve,") so views can test membership exactly with '
             '"\',approve,\' in htplus_allowed_transitions". This is a UX hint, not a '
             'security boundary - the guard in _htplus_apply_transition is.',
    )

    def _compute_htplus_allowed_transitions(self):
        """Compute the transitions the current user may run on each record.

        The value is comma-wrapped so a view testing ',lock,' cannot accidentally
        match a longer code such as 'unlock'.
        """
        for record in self:
            codes = record._htplus_available_transitions()
            record.htplus_allowed_transitions = ',%s,' % ','.join(codes) if codes else ','

    def _htplus_available_transitions(self):
        """Return the transition codes available on this record for this user.

        Returns:
            List of transition codes, in declaration order.
        """
        self.ensure_one()
        state = self.state if 'state' in self._fields else False
        return [
            code for code, spec in self._htplus_transitions.items()
            if state in spec['from'] and self._htplus_role_allowed(spec.get('role'))
        ]

    def _htplus_role_allowed(self, role):
        """Return whether the current user holds the group behind a role.

        An unmapped role returns False: a missing mapping hides the button
        rather than exposing it. The authoritative check raises instead, so the
        misconfiguration still surfaces the moment someone calls the action.

        Args:
            role: Role name from a transition spec, or None for no restriction.
        """
        if not role or self.env.su:
            return True
        xmlid = self._htplus_group_map.get(role)
        if not xmlid:
            return False
        return self.env.user.has_group(xmlid)

    def _htplus_require_role(self, role):
        """Raise unless the current user holds the group behind a role.

        Args:
            role: Role name from a transition spec, or None for no restriction.

        Raises:
            UserError: The role has no group mapped - a configuration error.
            AccessError: The user lacks the mapped group.
        """
        if not role or self.env.su:
            return
        xmlid = self._htplus_group_map.get(role)
        if not xmlid:
            raise UserError(_(
                'Workflow role "%(role)s" has no security group mapped on model '
                '%(model)s. Fill _htplus_group_map before using this transition.',
                role=role, model=self._name,
            ))
        if not self.env.user.has_group(xmlid):
            raise AccessError(_(
                'You do not have the required role to perform this action.'))

    def _htplus_apply_transition(self, code):
        """Run a declared transition on every record in self.

        The authoritative path for every state change: role check, source state
        check, guard hook, state write, after hook, event hook. Public ``action_*``
        methods are thin wrappers over this and must not write ``state`` directly,
        because they are reachable over RPC.

        Args:
            code: Transition code declared in _htplus_transitions.

        Raises:
            UserError: Unknown transition, or a record is in an illegal source state.
        """
        spec = self._htplus_transitions.get(code)
        if not spec:
            raise UserError(_(
                'Unknown transition "%(code)s" on %(model)s.',
                code=code, model=self._name,
            ))
        self._htplus_require_role(spec.get('role'))
        for record in self:
            if record.state not in spec['from']:
                raise UserError(_(
                    'Cannot run "%(code)s" on %(name)s: it is in state "%(state)s", '
                    'expected one of %(expected)s.',
                    code=code, name=record.display_name, state=record.state,
                    expected=', '.join(spec['from']),
                ))
            guard = getattr(record, '_htplus_guard_%s' % code, None)
            if guard:
                guard()
            record.state = spec['to']
            after = getattr(record, '_htplus_after_%s' % code, None)
            if after:
                after()
            record._htplus_on_transition(code, spec)
        return True

    def _htplus_on_transition(self, code, spec):
        """Hook called after a successful transition on a single record.

        Seam for the outbound event dispatcher: emitting here means every
        integration event is produced by the same authoritative path that
        changed the state.

        Args:
            code: Transition code that ran.
            spec: The transition spec that ran.
        """
        return

    # -- Generic wrappers ---------------------------------------------------
    # Present on every document so views and the web client can rely on them.
    # A model that does not declare the matching transition simply raises.

    def action_confirm(self):
        """Run the 'confirm' transition."""
        return self._htplus_apply_transition('confirm')

    def action_approve(self):
        """Run the 'approve' transition."""
        return self._htplus_apply_transition('approve')

    def action_lock(self):
        """Run the 'lock' transition."""
        return self._htplus_apply_transition('lock')

    def action_cancel(self):
        """Run the 'cancel' transition."""
        return self._htplus_apply_transition('cancel')

    def action_reset(self):
        """Run the 'reset' transition."""
        return self._htplus_apply_transition('reset')
