{
    "name": "HTPlus APS / Workforce Bridge",
    "version": "18.0.1.0.0",
    "summary": "Propose workforce assignments from a schedule run and report manning KPIs.",
    "description": """
Cross-capability behaviour that only makes sense when both APS and Workforce are
installed: a schedule run can propose assignments for its scheduled work orders,
and the planning dashboard gains shift and manning KPIs.

Owns no aggregate of its own - the schedule run belongs to APS, the assignment
belongs to Workforce. Installs itself as soon as both sides are present.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_aps_core", "htplus_workforce"],
    "data": [
        "views/htplus_workforce_views.xml",
        "views/htplus_schedule_button.xml",
    ],
    "auto_install": True,
    "application": False,
    "installable": True,
}
