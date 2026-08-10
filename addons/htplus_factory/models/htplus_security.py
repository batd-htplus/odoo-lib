from odoo import models, _
from odoo.exceptions import AccessError


class HtplusSecurityMixin(models.AbstractModel):
    _name = 'htplus.security.mixin'
    _description = 'HTPlus Role Checks'

    def _htplus_require_group(self, xmlid, message=None):
        """Raise an access error if the current user lacks the given security group.

        Args:
            xmlid: The security group XML ID to check.
            message: Optional error message to surface instead of the default.
        """
        if self.env.su:
            return
        if not self.env.user.has_group(xmlid):
            raise AccessError(message or _(
                'You do not have the required HTPlus role for this action.'
            ))

    def _htplus_require_planner(self):
        """Require the APS Planner (or Manager) role for the current user."""
        self._htplus_require_group(
            'htplus_factory.group_aps_planner',
            _('Only APS Planners (or Managers) can perform this action.'),
        )

    def _htplus_require_manager(self):
        """Require the APS Manager role for the current user."""
        self._htplus_require_group(
            'htplus_factory.group_aps_manager',
            _('Only APS Managers can perform this action.'),
        )
