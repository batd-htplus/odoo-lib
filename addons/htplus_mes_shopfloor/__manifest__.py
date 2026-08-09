{
    "name": "HTPlus MES Shop Floor",
    "version": "18.0.1.2.6",
    "summary": "Shop floor execution (MES lite): actuals, downtime, NG, issues, shift completion.",
    "description": """
HTPlus MES Shop Floor
=====================

Shop floor execution (MES lite): work order actuals, downtime tracking,
NG/scrap registration, issue management and shift completion reporting.
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
