{
    "name": "HTPlus Workforce",
    "version": "18.0.1.0.0",
    "summary": "Shifts, shift members and workforce assignment for manufacturing lines.",
    "description": """
HTPlus Workforce
================

Shift templates and production shifts, shift membership, shift actuals and the
assignment of employees to work. Sellable on its own: a plant can manage shifts
and manning without buying APS scheduling or MES shop-floor tracking.

Owns the assignment aggregate. APS states a *requirement* for a work order and a
bridge module translates it into an assignment here; MES records who actually
worked. Neither of them owns the assignment.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_factory",
        "hr",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/htplus_factory_rules.xml",
        "data/ir_sequence_data.xml",
        "views/htplus_workforce_views.xml",
        "views/htplus_shift_views.xml",
        "views/htplus_shift_actual_views.xml",
        "views/htplus_shift_member_views.xml",
        "views/htplus_shift_report.xml",
        "views/htplus_shift_report_templates.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "application": False,
    "installable": True,
    "auto_install": False,
}
