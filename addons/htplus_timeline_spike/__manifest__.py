{
    "name": "HTPlus Timeline Spike",
    "version": "18.0.1.2.1",
    "summary": "Spike: OCA web_timeline for mrp.workorder (screen 07 + 09).",
    "description": """
HTPlus Timeline Spike
=====================

Proof-of-concept integrating OCA web_timeline with mrp.workorder
(screens 07 and 09).
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": [
        "htplus_aps_core",
        "web_timeline",
    ],
    "data": [
        "views/workorder_timeline_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
