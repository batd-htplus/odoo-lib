{
    "name": "HTPlus Base",
    "version": "18.0.1.0.0",
    "summary": "Technical foundation for the HTPlus suite: declarative workflow and optimistic locking.",
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
    "data": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
