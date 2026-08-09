def migrate(cr, version):
    """Copy stashed schedule_* into Odoo date_start/date_finished (creates leaves)."""
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'htplus_wo_schedule_migrate'
        """
    )
    if not cr.fetchone():
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT id, schedule_start, schedule_end FROM htplus_wo_schedule_migrate")
    rows = cr.fetchall()
    Workorder = env['mrp.workorder']
    for workorder_id, schedule_start, schedule_end in rows:
        workorder = Workorder.browse(workorder_id)
        if not workorder.exists():
            continue
        vals = {}
        if schedule_start:
            vals['date_start'] = schedule_start
        if schedule_end:
            vals['date_finished'] = schedule_end
        if vals:
            workorder.write(vals)
    cr.execute("DROP TABLE IF EXISTS htplus_wo_schedule_migrate")
