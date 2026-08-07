{
    "name": "HTPlus AI Bridge",
    "version": "18.0.1.0.0",
    "summary": "Client bridge to the HTPlus AI Service (forecast, scheduling, assignment, chat).",
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_aps_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/htplus_ai_menus.xml",
        "views/htplus_ai_views.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
