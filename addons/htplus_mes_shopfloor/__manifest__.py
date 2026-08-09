{
    "name": "HTPlus MES Shop Floor",
    "version": "18.0.1.2.0",
    "summary": "Shop floor execution (MES lite): actuals, downtime, NG, issues, shift completion.",
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_aps_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/htplus_mes_menus.xml",
        "views/htplus_dashboard_views.xml",
        "views/htplus_mes_views.xml",
        "views/htplus_workforce_views.xml",
        "reports/htplus_production_daily_report.xml",
        "reports/htplus_production_daily_report_templates.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
