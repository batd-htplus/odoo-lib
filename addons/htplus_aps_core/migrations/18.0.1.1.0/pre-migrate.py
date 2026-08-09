def migrate(cr, version):
    """Stash shadow schedule_* before the columns are dropped on upgrade."""
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mrp_workorder' AND column_name = 'schedule_start'
        """
    )
    if not cr.fetchone():
        return
    cr.execute("DROP TABLE IF EXISTS htplus_wo_schedule_migrate")
    cr.execute(
        """
        CREATE TABLE htplus_wo_schedule_migrate AS
        SELECT id, schedule_start, schedule_end
        FROM mrp_workorder
        WHERE schedule_start IS NOT NULL OR schedule_end IS NOT NULL
        """
    )
