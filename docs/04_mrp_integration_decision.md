# MRP integration — decision (done)

**Status:** Option A implemented, 2026-08-09
**Scope:** `htplus_planning_base`, `htplus_aps_core`

## The decision

**`mrp.workorder` IS the schedule row.** APS extends MRP instead of duplicating it, so it inherits BOM, routing, stock moves and the MES actuals path for free.

```python
# htplus_aps_core: extend production + workorder
mrp.production  (+ htplus_plan_id, htplus_plan_line_id)
mrp.workorder   (+ schedule_run_id, line_id, machine_id, schedule_state, locked,
                   priority, schedule_conflict, material_ok, capacity_ok, machine_ok)
# htplus_planning_base: extend workcenter
mrp.workcenter  (+ factory_id, plant_id, line_id, capacity_per_hour)
```

## The key fix: use `date_start` / `date_finished`

Odoo's `mrp.workorder.date_start` / `date_finished` are **backed by a `resource.calendar.leaves` record** — that leave is what actually reserves work-center capacity. A parallel `schedule_start` / `schedule_end` was a "shadow schedule": it showed a plan but reserved nothing.

**Decision:** APS writes Odoo's `date_start` / `date_finished`. Capacity blocking, work-center load and standard MRP views come along for free. `schedule_state` and `locked` stay — they are genuinely HTPlus concepts. `htplus.schedule.change` tracks `('date_start', 'date_finished', 'machine_id', 'line_id', 'priority')` for audit/undo.

## Shift blocker (fixed)

`htplus_planning_base` originally inherited `hr.shift.template`, which **does not exist in Odoo 18 CE** (Enterprise-only). Replaced with a real model `_name = 'htplus.shift.template'`; shift affects work-center hours by syncing to `resource.calendar.attendance` — the Odoo-native way, which MRP capacity actually reads.

## Still to watch

- **Capacity defined twice:** `mrp.workcenter.capacity_per_hour` (HTPlus) vs Odoo's own `capacity` / `time_efficiency` / `resource_calendar_id`. Pick one before writing the scheduler against the wrong one.
- **4-level hierarchy** Factory → Plant → Line → Workcenter: Odoo only knows the last level, so capacity/load must be re-aggregated by hand. Confirm business really needs plant *and* line.
- **Undo:** old values must be captured *before* `super().write()`; gate the change-log on `schedule_run_id` to avoid auditing every internal MRP write.
- **Simulation must never write real work orders** — scenario holds its own lines and only materialises into `mrp.workorder` when applied.

## Effect on Gantt

Aligning on `date_start` makes `web_timeline` a good fit for the Gantt: view over `mrp.workorder` grouped by workcenter, drag writes those fields through the ORM → updates the leave → updates capacity. No custom controller. (See `third_party/web_timeline.md` for the license boundary.)
