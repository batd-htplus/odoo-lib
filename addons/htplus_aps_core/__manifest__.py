{
    "name": "HTPlus APS Core",
    "version": "18.0.1.8.2",
    "summary": "Demand planning, production planning, APS scheduling and simulation.",
    "description": """
HTPlus APS Core
===============

Demand planning, production planning, APS scheduling and simulation for
manufacturing operations.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_factory",
        "mail",
    ],
    "data": [
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "security/ir.model.access.csv",
        "security/htplus_factory_rules.xml",
        "views/htplus_aps_menus.xml",
        "views/htplus_dashboard_views.xml",
        "views/htplus_system_health_views.xml",
        "views/htplus_demand_plan_views.xml",
        "views/htplus_demand_import_views.xml",
        "views/htplus_master_data_import_views.xml",
        "views/htplus_production_plan_views.xml",
        "views/htplus_schedule_views.xml",
        "views/htplus_apply_views.xml",
        "views/htplus_simulation_views.xml",
        "views/htplus_search_views.xml",
        "views/htplus_settings_views.xml",
        "report/htplus_schedule_report_views.xml",
        "reports/htplus_schedule_report.xml",
        "reports/htplus_schedule_report_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "htplus_aps_core/static/src/gantt/htplus_gantt_actions.js",
            "htplus_aps_core/static/src/gantt/htplus_gantt_actions.xml",
            "htplus_aps_core/static/src/gantt/htplus_gantt.js",
            "htplus_aps_core/static/src/gantt/htplus_gantt.xml",
            "htplus_aps_core/static/src/gantt/htplus_gantt.scss",
        ],
    },
    "application": True,
    "installable": True,
    "auto_install": False,
}
