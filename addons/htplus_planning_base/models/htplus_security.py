from odoo import models, _
from odoo.exceptions import AccessError


class HtplusSecurityMixin(models.AbstractModel):
    _name = 'htplus.security.mixin'
    _description = 'HTPlus Role Checks'

    def _htplus_require_group(self, xmlid, message=None):
        if self.env.su:
            return
        if not self.env.user.has_group(xmlid):
            raise AccessError(message or _(
                'You do not have the required HTPlus role for this action.'
            ))

    def _htplus_require_planner(self):
        self._htplus_require_group(
            'htplus_planning_base.group_aps_planner',
            _('Only APS Planners (or Managers) can perform this action.'),
        )

    def _htplus_require_manager(self):
        self._htplus_require_group(
            'htplus_planning_base.group_aps_manager',
            _('Only APS Managers can perform this action.'),
        )
