import logging

_logger = logging.getLogger(__name__)

MODELS = (
    ('htplus.planning.rule', 'htplus_planning_rule'),
    ('htplus.priority.rule', 'htplus_priority_rule'),
    ('htplus.capacity.rule', 'htplus_capacity_rule'),
)


def migrate(cr, version):
    """Drop the three scheduling-rule models nothing ever consumed.

    They shipped a full configuration UI for planning policy, but no solver
    code read them - so anything typed in there silently had no effect. When
    capacity constraints are built for real the schema will follow whatever
    the solver needs, which is unlikely to match these tables.

    Removing the Python classes leaves the tables and their ir_model rows
    behind, so they are cleaned up here. Every statement is conditional, so
    the script is safe to re-run.

    A table holding rows is left alone and reported: a customer may have
    configured something a human should look at before it disappears.
    """
    for model, table in MODELS:
        cr.execute("SELECT to_regclass(%s)", ('public.' + table,))
        if cr.fetchone()[0] is None:
            continue
        cr.execute('SELECT count(*) FROM "%s"' % table)
        rows = cr.fetchone()[0]
        if rows:
            _logger.warning(
                '%s still holds %s row(s); leaving the table in place. '
                'Review it and drop it by hand once the contents are dealt with.',
                table, rows,
            )
            continue
        cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.model' AND name = %s",
                   ('model_' + table,))
        cr.execute("DELETE FROM ir_model_fields WHERE model = %s", (model,))
        cr.execute("DELETE FROM ir_model WHERE model = %s", (model,))
        cr.execute('DROP TABLE "%s"' % table)
        _logger.info('%s dropped (was empty).', table)
