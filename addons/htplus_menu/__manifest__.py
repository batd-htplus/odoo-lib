{
    "name": "HTPlus Menu",
    "version": "18.0.1.2.1",
    "summary": "Centralised app launcher and per-user bookmarks for Odoo Community.",
    "description": """
HTPlus Menu
===========

Replaces the stock apps drawer with a full-screen launcher, and adds per-user
bookmarks in the systray.

Bookmarks are private: a record rule restricts every row to its owner, and
bookmark URLs are limited to http(s) and instance-relative paths.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://htplus.software",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/menu_bookmark_security.xml",
        "views/main_menu_views.xml",
        "views/menu_bookmark_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "htplus_menu/static/src/components/**/*",
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    # auto_install with depends=["web"] would mean "install on every database,
    # always, with no way to opt out". An end-user application is installed
    # explicitly.
    "auto_install": False,
    "application": True,
    "installable": True,
}
