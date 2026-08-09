import { Component, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";

/**
 * Only these schemes may be handed to window.open. The server already
 * validates on write (menu.bookmark._check_url), but a bookmark could have
 * been stored before that constraint existed, so re-check on the client.
 */
const SAFE_SCHEMES = ["http:", "https:"];

function isSafeUrl(url) {
    if (typeof url !== "string" || !url) {
        return false;
    }

    if (url.startsWith("/") && !url.startsWith("//")) {
        return true;
    }
    try {
        return SAFE_SCHEMES.includes(new URL(url, window.location.origin).protocol);
    } catch {
        return false;
    }
}

export class Bookmark extends Component {
    static components = { Dropdown, DropdownItem };
    static props = {};
    static template = "htplus_menu.Bookmark";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.dropdown = useDropdownState();
        this.state = useState({ bookmarks: [], loading: false });
    }

    /**
     * Dropdown awaits whatever `beforeOpen` returns, so the list is populated
     * before the panel is painted. Returning the promise directly removes the
     * manual Deferred bookkeeping the previous version needed.
     */
    async onBeforeOpen() {
        await this.fetchBookmarks();
    }

    async fetchBookmarks() {
        this.state.loading = true;
        try {
            this.state.bookmarks = await rpc("/htplus_menu/bookmark/data");
        } catch {
            this.state.bookmarks = [];
            this.notification.add(_t("Could not load your bookmarks."), {
                type: "warning",
            });
        } finally {
            this.state.loading = false;
        }
    }

    openMyBookmarks() {
        this.dropdown.close();
        this.action.doAction("htplus_menu.menu_bookmark_action_my_bookmarks", {
            clearBreadcrumbs: true,
        });
    }

    openBookmark(bookmark) {
        this.dropdown.close();
        if (!isSafeUrl(bookmark.url)) {
            this.notification.add(_t("This bookmark points to an unsupported URL."), {
                type: "danger",
            });
            return;
        }
        if (bookmark.target === "_blank") {
            window.open(bookmark.url, "_blank", "noopener,noreferrer");
        } else {
            window.location.assign(bookmark.url);
        }
    }
}

registry
    .category("systray")
    .add("htplus_menu.bookmark", { Component: Bookmark }, { sequence: 10 });
