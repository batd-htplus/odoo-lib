"""Classify pre-existing dashboards once the dashboard_type column exists.

Dashboards that look like shift/manning boards (name mentions shift, "ca làm"
or "shift management") become dashboard_type='shift'; everything else stays
'production'. The column itself is created by htplus_aps_core, which upgrades
before this module, so it is always present here.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE htplus_dashboard_kpi
           SET dashboard_type = 'shift'
         WHERE dashboard_type = 'production'
           AND (name ILIKE '%%shift%%'
                OR name ILIKE '%%shift management%%'
                OR name ILIKE '%%ca làm%%')
    """)
