def migrate(cr, version):
    """Ensure every factory has a resource.calendar and link work centers."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    for factory in env['htplus.factory'].search([]):
        factory._ensure_resource_calendar()
        factory.action_apply_calendar_to_workcenters()
    templates = env['htplus.shift.template'].search([
        ('active', '=', True),
        '|', ('factory_id', '!=', False), ('resource_calendar_id', '!=', False),
    ])
    if templates:
        templates.action_sync_to_calendar()
