{
    "name": "HTPlus APS / MES Bridge",
    "version": "18.0.1.0.0",
    "summary": "Feed shop-floor actuals into the APS dashboard KPIs.",
    "description": """
Cross-capability behaviour that only makes sense when both APS and MES are
installed: the planning dashboard gains execution KPIs computed from work order
actuals, downtime and NG.

Owns no aggregate of its own - the dashboard belongs to APS, the actuals belong
to MES. Installs itself as soon as both sides are present.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_aps_core", "htplus_mes_shopfloor"],
    "data": ["views/htplus_dashboard_views.xml"],
    "auto_install": True,
    "application": False,
    "installable": True,
}
