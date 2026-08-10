import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Drop htplus.planning.parameter, superseded by ir.config_parameter.

    The model duplicated Odoo's own key/value store and nothing ever read it.
    Removing the Python class leaves the table and its ir_model rows behind, so
    they are cleaned up here rather than lingering as dead weight in every
    customer database.

    Safe to re-run: every statement is conditional.
    """
    cr.execute("SELECT to_regclass('public.htplus_planning_parameter')")
    if cr.fetchone()[0] is None:
        return
    cr.execute("SELECT count(*) FROM htplus_planning_parameter")
    rows = cr.fetchone()[0]
    if rows:
        # Never destroy data silently: leave the table for a human to look at.
        _logger.warning(
            'htplus_planning_parameter still holds %s row(s); leaving the table '
            'in place. Move them to ir.config_parameter and drop it by hand.',
            rows,
        )
        return
    cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.model' "
               "AND name = 'model_htplus_planning_parameter'")
    cr.execute("DELETE FROM ir_model_fields WHERE model = 'htplus.planning.parameter'")
    cr.execute("DELETE FROM ir_model WHERE model = 'htplus.planning.parameter'")
    cr.execute("DROP TABLE htplus_planning_parameter")
    _logger.info('htplus_planning_parameter dropped (was empty).')
