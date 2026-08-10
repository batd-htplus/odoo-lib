{
    "name": "HTPlus Workforce / Skills Bridge",
    "version": "18.0.1.0.0",
    "summary": "Match employees to work by skill when hr_skills is installed.",
    "description": """
Cross-capability behaviour that only makes sense when both Workforce and Odoo's
Skills are installed: the production skill taxonomy, the skill matrix screens,
and the skill check that runs when an assignment is validated.

Without this module a plant still assigns people to shifts - it simply does not
filter them by qualification.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_workforce", "hr_skills"],
    "data": [
        "data/htplus_skill_data.xml",
        "views/htplus_skill_views.xml",
    ],
    "auto_install": True,
    "application": False,
    "installable": True,
}
