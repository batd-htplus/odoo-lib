# HTPlus Menu

Full-screen app launcher plus per-user bookmarks for Odoo 18 Community.

## What it does

- Replaces the stock apps drawer with a client action (`htplus_menu.action_open_main_menu`)
  showing every app as a tile, with type-to-search wired to the command palette.
- Adds a bookmark dropdown in the systray, and an "Add Bookmark" entry in the
  cog menu that bookmarks the current page.

## Security model

Bookmarks are private per user, enforced at the ORM layer:

- `security/ir.model.access.csv` grants CRUD to `base.group_user`.
- `security/menu_bookmark_security.xml` adds a record rule limiting every row to
  `user_id = user.id`, plus a separate rule letting `base.group_system` see all.

The `[('user_id','=',uid)]` domain on the action is a UI convenience only — it
is not a security boundary, and must not be relied on as one.

Bookmark URLs are restricted by `menu.bookmark._check_url` to `http`, `https`
and instance-relative paths. `javascript:`, `data:` and protocol-relative
(`//host`) URLs are rejected, because the stored value is passed to
`window.open()` in the systray dropdown. The client re-checks in
`bookmark.js:isSafeUrl` to cover rows created before the constraint existed.

## Endpoints

| Route | Type | Notes |
|---|---|---|
| `/htplus_menu/bookmark/data` | `json`, `auth='user'`, `readonly=True` | explicit field projection, capped at 200 rows |
| `/htplus_menu/bookmark/add`  | `json`, `auth='user'` | binds `user_id` to the session, returns `{success, bookmark}` |

`type='json'` is correct on Odoo 18 — the `jsonrpc` routing type only exists
from Odoo 19.

## Assets

Only `static/src/components/**/*` is bundled. Anything placed outside that tree
is not loaded.

## CSS namespacing

All selectors are scoped under `.o_htplus_main_menu` / `o_htplus_*`.
`web.assets_backend` is a global bundle, so generic class names such as
`.background` or `.module-icon` leak into every other module.

## Tests

```bash
make test M=htplus_menu
```

Covers the record rule (cross-user read/write/unlink), URL validation, the
`ondelete='cascade'` on `user_id`, and the default owner.

## Translations

No `.po` files are shipped. Generate a template from a database with the module
installed:

```bash
odoo -d <db> --i18n-export=htplus_menu.pot --modules=htplus_menu --stop-after-init
```

## Upstream

Forked from the community `main_menu` module. The rename is now complete —
registry keys, routes and CSS classes are all namespaced under `htplus_menu`.
