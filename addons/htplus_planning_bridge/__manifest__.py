{
    "name": "HTPlus Planning Bridge",
    "version": "18.0.1.1.7",
    "summary": "Client bridge to the HTPlus Planning Engine (forecast, scheduling, assignment, assistant).",
    "description": """
HTPlus Planning Bridge
======================

Client bridge to the HTPlus Planning Engine covering forecast, scheduling,
assignment and the planning assistant.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_aps_core",
    ],
    "data": [
        "views/htplus_schedule_run_views.xml",
        "views/htplus_demand_plan_views.xml",
        "security/ir.model.access.csv",
        "security/htplus_planning_rules.xml",
        "views/htplus_planning_menus.xml",
        "views/htplus_planning_views.xml",
        "views/htplus_search_views.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "data/htplus_planning_config_data.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
