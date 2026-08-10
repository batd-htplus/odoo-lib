from odoo import models


class HtplusWorkflowMixin(models.AbstractModel):
    """Bind HTPlus workflow roles to the real Odoo security groups.

    ``htplus_base`` owns the transition mechanism but must stay neutral, so it
    ships an empty role map. The domain layer fills it here - once, for every
    model that uses the mixin.

    The groups are declared here in ``htplus_factory`` and keep the same record
    names they always had, so every ``ir.model.access.csv`` and ``has_group()``
    call across the suite keeps working unchanged.
    """

    _inherit = 'htplus.workflow.mixin'

    _htplus_group_map = {
        'user': 'htplus_factory.group_aps_user',
        'planner': 'htplus_factory.group_aps_planner',
        'manager': 'htplus_factory.group_aps_manager',
        'operator': 'htplus_factory.group_mes_operator',
    }
