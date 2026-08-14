{
    "name": "HTPlus Workforce / Time Off Bridge",
    "version": "18.0.1.0.0",
    "summary": "Surface employee time off alongside the shift calendar.",
    "description": """
Cross-capability behaviour that only makes sense when both Workforce and Odoo's
Time Off are installed: leave requests appear in the HTPlus shift calendar so a
line leader sees who is unavailable before assigning a shift.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_workforce", "hr_holidays"],
    "data": [
        "security/htplus_factory_rules.xml",
        "views/htplus_leave_views.xml",
    ],
    "auto_install": True,
    "application": False,
    "installable": True,
}
