# mrp_multi_level (OCA manufacture) — harvested, not vendored

**Source:** `manufacture-18.0/mrp_multi_level` (OCA/manufacture 18.0)
**License:** LGPL-3
**Location in repo:** reference tree only (`manufacture-18.0/`, gitignored). **Not** in `addons_vendor/`.

## Status: evaluated and harvested into HTPlus

HTPlus already owns Demand / Production Plan. Installing OCA Multi Level beside that would
create a parallel MRP stack (`mrp.planned.order`, `mrp.area`, procure wizard). Instead we
copied the **procure pattern** only:

| OCA idea | HTPlus adaptation |
|---|---|
| Select planned lines → wizard → create MO/PO | Plan already creates MOs via `action_create_productions` |
| One “execute” step opening the result | `htplus.production.plan.action_create_schedule` → `htplus.schedule.run` |
| Attach supply documents to the plan | Attach `mrp.workorder` via `schedule_run_id` |
| Calendar-aware finish (`mrp_warehouse_calendar`) | `resource.calendar.plan_hours` on WC when proposing WO dates |
| (HTPlus addition, not OCA) | Greedy propose dates per WC; `action_calculate` marks overlaps; refuse stealing confirmed/locked WOs |

Related reference modules in the same tree (also not vendored):

- `mrp_workorder_sequence` — CE workorders already have `sequence`; not copied.
- `mrp_warehouse_calendar` — pattern for calendar-aware finish dates; adapted via WC
  `resource_calendar_id` (factory calendar sync in `htplus_planning_base`).

## Direct dependency

None. No first-party module `depends` on `mrp_multi_level`.
