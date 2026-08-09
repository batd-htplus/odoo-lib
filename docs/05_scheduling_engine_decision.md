# Scheduling engine — decision (done)

**Status:** CP-SAT implemented; Odoo wiring via bridge → simulation scenario, 2026-08-09
**Scope:** `services/planning`, `htplus.schedule.run.algorithm`, `htplus_planning_bridge`

## What exists

`htplus.schedule.run.algorithm` offers `manual` / `rule_engine` / `solver_cpsat`.

- FastAPI: greedy (`rule_engine`) + OR-Tools CP-SAT (`solver_cpsat`) behind `app/scheduler/`.
- Odoo: with `htplus_planning_bridge` installed, **Run Solver** calls
  `schedule_recommend(..., algorithm=...)`, polls the async job, and writes results into
  `htplus.simulation.scenario` lines (`simulated_start` / `simulated_end`).
- Real `mrp.workorder` dates change only when the user runs **Apply** on the scenario.

`manual` still uses the local copy-from-base path (no HTTP).

## Decision

Implement `solver_cpsat` with **OR-Tools CP-SAT**, in-process in the FastAPI service, behind an adapter so the engine can be swapped without touching routes or the Odoo contract.

- **Why OR-Tools:** Apache-2.0, Python-native (no extra runtime/process), and CP-SAT is the textbook fit for job-shop / RCPSP scheduling (interval variables + no-overlap + tardiness/makespan objectives).
- **Timefold rejected:** solid (Apache-2.0) but JVM-only — would add a second runtime, image and deploy surface for a capability OR-Tools already covers in-process.
- **Greedy kept** as `rule_engine` — the always-available fallback.
- **Wire target = scenario to review** (not direct WO write) — safer for planners; apply is explicit.

## Model (same simplification as greedy)

- One workcenter per work order (`routing[0]`, default `1`); `duration_hours = max(ceil(qty / 10.0), 1)`.
- One interval per work order, fixed duration, integer hour axis, horizon 30 days.
- `AddNoOverlap` per workcenter (greedy approximates this with a cursor).
- Objective: `min sum(tardiness)` by default, or `min max(end)` for makespan.
- Solver budget 5s; job is async (`/api/v1/job/{id}`). Infeasible / timeout → fall back to greedy, label result `cpsat_fallback_greedy`.

## Adapter boundary

```
app/scheduler/
  base.py     Scheduler protocol: schedule(workorders, constraints, objective) -> dict
  greedy.py   wraps services.greedy_schedule unchanged
  cpsat.py    OR-Tools CP-SAT implementation
  __init__.py registry: {"rule_engine": greedy, "solver_cpsat": cpsat}
```

`ScheduleRequest.algorithm` accepts the same two values as `htplus.schedule.run.algorithm` (`manual` = human edits the Gantt, no API equivalent).

## Deferred

- Richer constraints (shifts, holidays, machine capacity) still largely unused by the engine.
- Full e2e with real factory/BOM/work orders (HTTP path smoke-tested: `schedule_recommend` → job poll → `greedy_fallback`).
