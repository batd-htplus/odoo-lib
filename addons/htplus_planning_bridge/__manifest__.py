{
    "name": "HTPlus Planning Bridge",
    "version": "18.0.1.1.2",
    "summary": "Client bridge to the HTPlus Planning Engine (forecast, scheduling, assignment, assistant).",
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_aps_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/htplus_planning_menus.xml",
        "views/htplus_planning_views.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "data/htplus_planning_config_data.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
