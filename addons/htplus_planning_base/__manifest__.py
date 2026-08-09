{
    "name": "HTPlus APS Planning Base",
    "version": "18.0.1.5.2",
    "summary": "Master data foundation for HTPlus APS/MES.",
    "description": """
HTPlus APS Planning Base
========================

Master data foundation for the HTPlus APS/MES suite: factories, machines,
production lines, shift templates and skill definitions used across the
planning, scheduling and shop floor modules.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "mrp",
        "resource",
        "hr",
        "hr_skills",
        "hr_holidays",
    ],
    "data": [
        "security/htplus_groups.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/htplus_skill_data.xml",
        "data/htplus_admin_groups.xml",
        "views/htplus_planning_base_menus.xml",
        "views/htplus_factory_views.xml",
        "views/htplus_machine_views.xml",
        "views/htplus_shift_views.xml",
        "views/htplus_shift_actual_views.xml",
        "views/htplus_shift_member_views.xml",
        "views/htplus_rule_views.xml",
        "views/htplus_skill_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
