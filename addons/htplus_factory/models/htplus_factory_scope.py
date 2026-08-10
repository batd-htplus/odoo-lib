from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtplusFactoryScopeMixin(models.AbstractModel):
    """Carry a stored, indexed ``factory_id`` so record rules stay cheap.

    Record rules run on *every* read and search. Writing them as relational
    walks - ``workcenter_id.line_id.plant_id.factory_id`` - costs a subquery per
    level on every single query, which on a few years of work orders is the
    difference between a dashboard that loads and one that does not.

    So the factory is denormalised onto each scoped model, indexed, and the rule
    becomes one condition on one column. The price is that the denormalised
    value must never drift: a stale ``factory_id`` is not a display bug, it is a
    user of factory A reading factory B. Hence:

    * every model declares its own ``@api.depends`` covering the *whole* path -
      miss one link and moving a workcenter between factories leaves the old
      value behind;
    * ``_check_htplus_factory_consistency`` re-asserts the invariant on write,
      so a direct SQL fix or a bad import surfaces instead of silently opening
      access;
    * the field is ``readonly=False`` so master data that owns its factory
      outright (a plant, a shift template) can simply set it.

    Declaring a scoped model::

        class MrpWorkorder(models.Model):
            _inherit = ['mrp.workorder', 'htplus.factory.scope.mixin']
            _htplus_factory_path = 'workcenter_id.factory_id'

            @api.depends('workcenter_id', 'workcenter_id.factory_id')
            def _compute_htplus_factory_id(self):
                return super()._compute_htplus_factory_id()
    """

    _name = 'htplus.factory.scope.mixin'
    _description = 'HTPlus Factory Scoping'

    # Dotted path from this model to its factory. None means the field is set
    # directly on the record instead of derived.
    _htplus_factory_path = None

    factory_id = fields.Many2one(
        'htplus.factory',
        string='Factory',
        index=True,
        store=True,
        readonly=False,
        compute='_compute_htplus_factory_id',
        help='Factory this record belongs to. Drives record-rule access.',
    )

    def _compute_htplus_factory_id(self):
        """Walk ``_htplus_factory_path`` to the owning factory.

        Records whose model declares no path keep whatever was set on them, so
        the same field serves both derived and directly-owned records.
        """
        path = self._htplus_factory_path
        if not path:
            for record in self:
                record.factory_id = record.factory_id
            return
        parts = path.split('.')
        for record in self:
            value = record
            for part in parts:
                value = value[part] if value else False
                if not value:
                    break
            record.factory_id = value or False

    @api.constrains('factory_id')
    def _check_htplus_factory_consistency(self):
        """Assert the denormalised factory still matches the relational truth.

        Compute alone is not enough to lean on for access control: data arrives
        through imports, migration scripts and direct SQL too.
        """
        path = self._htplus_factory_path
        if not path:
            return
        parts = path.split('.')
        for record in self:
            value = record
            for part in parts:
                value = value[part] if value else False
                if not value:
                    break
            expected = value or False
            if expected and record.factory_id != expected:
                raise ValidationError(_(
                    '%(record)s points at factory "%(actual)s" but belongs to '
                    '"%(expected)s". Refusing to store an access scope that does '
                    'not match the data.',
                    record=record.display_name,
                    actual=record.factory_id.display_name or _('none'),
                    expected=expected.display_name,
                ))


class ResUsers(models.Model):
    """Which factories a user may see."""

    _inherit = 'res.users'

    htplus_factory_ids = fields.Many2many(
        'htplus.factory',
        'htplus_factory_users_rel', 'user_id', 'factory_id',
        string='Allowed Factories',
        help='Factories this user may access. Empty means none: grant the '
             '"All Factories" role for unrestricted access rather than relying '
             'on an empty list.',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        """Let a user see their own factory scope without admin rights."""
        return super().SELF_READABLE_FIELDS + ['htplus_factory_ids']

    def write(self, vals):
        """Clear cached record-rule domains when a user's factory scope changes.

        ir.rule domains are cached per user. Without this, granting or revoking
        a factory has no effect until something else happens to clear the
        cache - access silently keeps following the old scope.
        """
        result = super().write(vals)
        if 'htplus_factory_ids' in vals:
            self.env.registry.clear_cache()
        return result
