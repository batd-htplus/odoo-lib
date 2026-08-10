import logging

_logger = logging.getLogger(__name__)

# XML ids that used to be declared by htplus_planning_base and now belong here.
# Reassigning them keeps the *same* database rows: security groups keep their
# members, menus keep their position, ACL lines keep their identity.
_ADOPTED_XMLIDS = (
    'module_category_htplus_aps',
    'group_aps_user',
    'group_aps_planner',
    'group_aps_manager',
    'group_mes_operator',
    'htplus_aps_menu_root',
    'htplus_aps_menu_master_data',
)

_ADOPTED_PREFIXES = (
    # ir.model entries: their XML id belongs to whichever module defines the model.
    'model_htplus_factory',
    'model_htplus_plant',
    'model_htplus_line',
    'model_htplus_machine',
    # ACL lines for the models that moved with this module.
    'access_htplus_factory',
    'access_htplus_plant',
    'access_htplus_line',
    'access_htplus_machine',
    # Views and actions of the moved models.
    'htplus_factory_',
    'htplus_plant_',
    'htplus_line_',
    'htplus_machine_',
    'action_htplus_factory',
    'action_htplus_plant',
    'action_htplus_line',
    'action_htplus_machine',
)


def pre_init_hook(env):
    """Take ownership of the records htplus_planning_base used to declare.

    Runs before this module's data files load. Without it, upgrading
    htplus_planning_base after the split would delete the security groups it no
    longer declares - taking every user's role assignment with them - and this
    module would then recreate them empty.

    Idempotent: a second run finds nothing left to adopt.
    """
    exact = list(_ADOPTED_XMLIDS)
    like = ['%s%%' % prefix for prefix in _ADOPTED_PREFIXES]
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'htplus_factory'
         WHERE module = 'htplus_planning_base'
           AND (name = ANY(%s) OR name LIKE ANY(%s))
        """,
        (exact, like),
    )
    if env.cr.rowcount:
        _logger.info(
            'htplus_factory: adopted %s record(s) from htplus_planning_base.',
            env.cr.rowcount,
        )
