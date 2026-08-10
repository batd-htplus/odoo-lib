{
    "name": "HTPlus Factory / Maintenance Bridge",
    "version": "18.0.1.0.0",
    "summary": "Keep machine status in step with open maintenance requests.",
    "description": """
Cross-capability behaviour that only makes sense when both HTPlus Factory and
Odoo's Maintenance are installed: a machine points at its equipment record, and
an open maintenance request drops the machine out of 'operational' so planning
stops treating it as available.

Uses a plain Many2one rather than _inherits delegation - see the model docstring
for why.
    """,
    "author": "Ba.TD",
    "maintainer": "Ba.TD",
    "website": "https://www.htplus.jp/",
    "license": "LGPL-3",
    "category": "HTPlus",
    "depends": ["htplus_factory", "maintenance"],
    "data": ["views/htplus_machine_views.xml"],
    "auto_install": True,
    "application": False,
    "installable": True,
}
