# hr_shift (Employees Shifts)

**Source:** https://github.com/OCA/shift-planning/tree/18.0/hr_shift
**Version evaluated:** 18.0.1.1.2
**License:** AGPL-3.0-or-later
**Location:** not vendored - removed (see below). Was previously at
`addons_vendor/hr_shift/`.

## Status: evaluated and removed, not part of this repo

This module was vendored briefly while investigating the `hr.shift.template`
blocker described below, then removed: it duplicates functionality
`htplus_planning_base` already owns (`htplus.shift.template`,
`htplus.production.shift`, `htplus.workforce.assignment`), and no first-party
module ever depended on it. Keeping an unused, functionally-overlapping copy
around only invites someone to `depends: ["hr_shift"]` later without hitting
the license question below. This file stays as the record of that decision -
re-fetch it from the source URL above if the tradeoff ever needs revisiting.

## What it provides

A real, `_name`-defined `hr.shift.template` (plus `hr.shift.planning`,
`hr.shift.planning.shift/.line`, a drag-and-drop planning UI, and inherits on
`hr.employee.base`, `resource.calendar`, `resource.calendar.leaves`,
`res.company`, `res.config.settings`). Depends on `hr` and `base_sparse_field`
only - both are Community.

This is the module `htplus_planning_base/models/htplus_shift.py` originally
assumed existed as `hr.shift.template` before it was vendored here. If you are
looking at this file because you are wondering "why doesn't HTPlus just
`_inherit` this instead of defining its own `htplus.shift.template`?" - that is
exactly the right question, and the answer is licensing, not missing
functionality.

## Why `htplus_planning_base` does not depend on it

`htplus_planning_base` is the foundation of the entire first-party tree:
`htplus_aps_core` depends on it, and `htplus_mes_shopfloor` /
`htplus_planning_bridge` depend on `htplus_aps_core`. If
`htplus_planning_base` depended on `hr_shift` (AGPL-3), the AGPL-3 combined-work
obligation (see `docs/third_party/web_timeline.md` for the mechanics) would
propagate through that entire chain - i.e. essentially the whole HTPlus
codebase, not an isolated view layer. That is a materially different, and much
larger, decision than the one made for `web_timeline` (which only taints one
thin, view-only module).

`htplus_planning_base/models/htplus_shift.py` instead defines its own
`htplus.shift.template` (`_name`, not `_inherit`), staying LGPL-3.

## If this module is adopted later

Follow the same pattern as `htplus_timeline_spike`: a separate, thin,
AGPL-3-licensed adapter module (e.g. `htplus_shift_planning_adapter`) that
`_inherit`s `hr.shift.template` / uses `hr.shift.planning` for the UI, and that
no LGPL-3 HTPlus module ever depends on. Business logic (capacity rules,
conflict checks, HTPlus-specific fields) stays in the LGPL-3 core models and is
exposed to the adapter through normal Odoo inheritance, not the other way
around.

## Direct dependency

No first-party module. If that changes, update this file and
`docs/third_party/web_timeline.md`'s cross-reference.
