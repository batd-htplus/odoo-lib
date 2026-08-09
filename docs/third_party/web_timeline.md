# web_timeline

**Source:** https://github.com/OCA/web/tree/18.0/web_timeline
**Version vendored:** 18.0.1.0.3
**License:** AGPL-3.0-or-later
**Location:** `addons_vendor/web_timeline/` (unmodified vendor copy)

## Purpose

Adds a `<timeline>` view type to Odoo (wraps `vis-timeline`), with group-by
swimlanes and drag-to-write against the ORM. Candidate for screens 07 (Gantt)
and 09 (Shift Calendar) instead of hand-writing an OWL Gantt component or
adopting Frappe Gantt (which has no group/swimlane concept - see
`docs/04_mrp_integration_decision.md`).

## Used by

`addons/htplus_timeline_spike/` only, at present. Status: **spike, not yet a
committed dependency** - see the open question below.

## License boundary - read before adding a second consumer

`web_timeline` is AGPL-3. Any Odoo module that `depends` on it runs in the
same process and forms a combined work, so it inherits AGPL-3 obligations,
including section 13 (network users may demand source of the whole running
system).

Rule enforced in this repo: **only a thin, view-only module may depend on
`web_timeline`.** `htplus_aps_core` - the actual scheduling/APS logic, and the
part of the codebase that is HTPlus's IP - must never depend on it, directly
or transitively. If the timeline view is adopted for real, the boundary module
stays AGPL-3 and contains XML view/action/menu records only; no business logic
moves into it.

## Direct dependency

No. `htplus_aps_core` and other LGPL-3 HTPlus modules do not import or depend
on `web_timeline` or on `htplus_timeline_spike`.

## Field mapping (option A — done)

The spike binds the timeline to `date_start` / `date_finished` on
`mrp.workorder`, which are backed by `resource.calendar.leaves` and reserve
work-center capacity. Dragging a bar writes those fields through the ORM.

## Replacement strategy

If `web_timeline` is dropped later (license concerns, or a better fit is
found), only the boundary module needs to change: re-point its view
declarations at another view type/library. `htplus_aps_core`'s domain models
(`mrp.workorder` extensions, `htplus.schedule.run`, ...) are untouched, since
they were never aware of `web_timeline` in the first place.
