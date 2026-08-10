import logging

_logger = logging.getLogger(__name__)

# Everything htplus_planning_base used to declare that now belongs here. Same
# database rows keep their identity: sequences keep their next number, skill
# types keep the employees attached to them, shifts keep their views.
_ADOPTED_PREFIXES = (
    'model_htplus_shift',
    'model_htplus_production_shift',
    'model_htplus_workforce',
    'access_htplus_shift',
    'access_htplus_production_shift',
    'access_htplus_workforce',
    'htplus_shift',
    'htplus_production_shift',
    'htplus_workforce',
    'htplus_skill',
    'hr_skill_type_',
    'hr_skill_level_',
    'hr_skill_',
    'seq_htplus_',
    'view_htplus_shift',
    'action_htplus_shift',
    'menu_htplus_shift',
    'menu_htplus_workforce',
    'menu_htplus_skill',
)


def pre_init_hook(env):
    """Take ownership of the records htplus_planning_base used to declare.

    Runs before this module's data files load, so the rows are re-parented
    before Odoo would otherwise drop them as orphans of a module that no longer
    declares them. Idempotent.
    """
    like = ['%s%%' % prefix for prefix in _ADOPTED_PREFIXES]
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'htplus_workforce'
         WHERE module = 'htplus_planning_base'
           AND name LIKE ANY(%s)
        """,
        (like,),
    )
    if env.cr.rowcount:
        _logger.info(
            'htplus_workforce: adopted %s record(s) from htplus_planning_base.',
            env.cr.rowcount,
        )
