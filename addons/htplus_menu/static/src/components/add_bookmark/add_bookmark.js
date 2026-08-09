import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export class AddBookmark extends Component {
    static template = "htplus_menu.AddBookmark";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.notification = useService("notification");
    }

    /**
     * The previous version fired the RPC without awaiting it and without a
     * catch, so a rejected request - including the URL validation error raised
     * by menu.bookmark._check_url - was swallowed and the user got no feedback
     * at all.
     */
    async addBookmark() {
        let result;
        try {
            result = await rpc("/htplus_menu/bookmark/add", {
                name: document.title,
                url: window.location.href,
            });
        } catch {
            this.notification.add(_t("Could not save the bookmark."), { type: "danger" });
            return;
        }

        if (!result || !result.success) {
            this.notification.add(_t("Could not save the bookmark."), { type: "danger" });
        } else if (result.existing) {
            this.notification.add(_t("This page is already bookmarked."), { type: "info" });
        } else {
            this.notification.add(_t("Bookmark added."), { type: "success" });
        }
    }
}

registry
    .category("cogMenu")
    .add("htplus_menu.add-bookmark", { Component: AddBookmark }, { sequence: 1 });
