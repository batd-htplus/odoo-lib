{
    "name": "HTPlus Factory",
    "version": "18.0.1.0.0",
    "summary": "Manufacturing foundation: factory, plant, line, machine and access scoping.",
    "description": """
HTPlus Factory
==============

The manufacturing foundation every HTPlus capability sits on: the
Factory -> Plant -> Line -> Workcenter hierarchy, machines, factory holidays,
the security groups and the calendar bridge.

Deliberately free of planning policy (capacity/priority rules live in the APS
module) and of optional apps such as HR skills or Maintenance, which are wired
in through auto-installed bridge modules instead.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_base",
        "mrp",
        "resource",
    ],
    "data": [
        "security/htplus_groups.xml",
        "security/ir.model.access.csv",
        "security/htplus_factory_rules.xml",
        "data/htplus_admin_groups.xml",
        "views/htplus_factory_menus.xml",
        "views/htplus_factory_views.xml",
        "views/htplus_machine_views.xml",
        "views/htplus_factory_holiday_views.xml",
        "views/htplus_users_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "application": False,
    "installable": True,
    "auto_install": False,
}
