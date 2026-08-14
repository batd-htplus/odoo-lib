from odoo import api, models, tools


class IrUiMenu(models.Model):
    """Keep the HTPlus APS app hidden until the user can actually see data.

    Menu visibility otherwise follows groups only, so a user holding an APS or
    MES group but no factory scope would land inside an app where every record
    is blocked by a record rule. The app only makes sense with data behind it,
    so hide it until the user has at least one factory or the All Factories
    role.
    """

    _inherit = 'ir.ui.menu'

    @api.model
    @tools.ormcache('frozenset(self.env.user.groups_id.ids)', 'debug')
    def _visible_menu_ids(self, debug=False):
        visible = set(super()._visible_menu_ids(debug))
        user = self.env.user
        if (
            not user._is_admin()
            and not user.has_group('htplus_factory.group_htplus_all_factories')
            and not user.htplus_factory_ids
        ):
            app = self.env.ref('htplus_factory.htplus_aps_menu_root',
                               raise_if_not_found=False)
            if app:
                hidden = self.with_context(
                    **{'ir.ui.menu.full_list': True}).search(
                        [('id', 'child_of', app.ids)])
                visible -= set(hidden.ids)
        return visible
