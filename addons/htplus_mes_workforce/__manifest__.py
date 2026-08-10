{
    "name": "HTPlus MES / Workforce Bridge",
    "version": "18.0.1.0.0",
    "summary": "Turn a confirmed workforce assignment into a shop-floor actual.",
    "description": """
Cross-capability behaviour that only makes sense when both Workforce and MES are
installed: confirming an assignment opens the matching work order actual.

Owns no aggregate of its own - the assignment belongs to Workforce, the actual
belongs to MES. Installs itself as soon as both sides are present.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_mes_shopfloor", "htplus_workforce"],
    "data": [
        "security/ir.model.access.csv","views/htplus_workforce_views.xml"],
    "auto_install": True,
    "application": False,
    "installable": True,
}
