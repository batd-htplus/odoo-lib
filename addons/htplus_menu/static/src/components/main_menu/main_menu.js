import { Component, onWillStart, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MAIN_MENU_XMLID = "htplus_menu.main_menu_root";

export class MainMenuAction extends Component {
    static props = { ...standardActionServiceProps };
    static template = "htplus_menu.MainMenu";

    setup() {
        // useState: the previous version used a plain object, so the
        // useEffect dependency `() => [this.state.isOpen]` never saw a change
        // and the keyboard listener was never re-attached or torn down.
        this.state = useState({ isOpen: true });
        this.commandPaletteOpen = false;

        this.menuService = useService("menu");
        this.commandService = useService("command");

        this.apps = this.menuService
            .getApps()
            .filter((app) => app.xmlid !== MAIN_MENU_XMLID);

        this.deg = `${90 + (180 * Math.atan(window.innerHeight / window.innerWidth)) / Math.PI}deg`;

        onWillStart(async () => {
            this.userIsAdmin = await user.hasGroup("base.group_system");
        });

        useEffect(
            (isOpen) => {
                if (!isOpen) {
                    return;
                }
                const openMainPalette = (ev) => {
                    if (
                        // Was `this.commandServiceOpen` - a property that does
                        // not exist, so the guard was always undefined and the
                        // palette re-opened on every single keypress.
                        !this.commandPaletteOpen &&
                        ev.key.length === 1 &&
                        !ev.ctrlKey &&
                        !ev.altKey &&
                        !ev.metaKey
                    ) {
                        this.commandPaletteOpen = true;
                        this.commandService.openMainPalette(
                            { searchValue: `/${ev.key}` },
                            () => {
                                this.commandPaletteOpen = false;
                            }
                        );
                    }
                };
                window.addEventListener("keydown", openMainPalette);
                return () => {
                    window.removeEventListener("keydown", openMainPalette);
                    this.commandPaletteOpen = false;
                };
            },
            () => [this.state.isOpen]
        );
    }

    onClickModule(menu) {
        if (menu) {
            this.menuService.selectMenu(menu);
        }
    }
}

// Namespaced on this module. The key previously carried the upstream
// main_menu namespace this addon was forked from; it must stay in sync with
// the <field name="tag"> in views/main_menu_views.xml.
registry.category("actions").add("htplus_menu.action_open_main_menu", MainMenuAction);
