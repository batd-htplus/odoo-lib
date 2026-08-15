{
    "name": "HTPlus Base",
    "version": "18.0.1.1.1",
    "summary": "Technical foundation for the HTPlus suite: declarative workflow, optimistic locking and background jobs.",
    "description": """
HTPlus Base
===========

Infrastructure mixins shared by every HTPlus module. Contains no business model,
no application menu and no business data: nothing here knows what a factory, a
work order or a shift is.

See README.md for the public extension contract.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/htplus_job_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
