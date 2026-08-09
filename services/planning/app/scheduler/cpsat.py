from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ortools.sat.python import cp_model

from .greedy import GreedyScheduler

# See docs/05_scheduling_engine_decision.md for the license/runtime
# evaluation (OR-Tools: Apache-2.0, Python-native, verified against
# github.com/google/or-tools's LICENSE file) and the model description.

_HORIZON_DAYS = 30
_TIME_LIMIT_SECONDS = 5.0


class CpSatScheduler:
    """OR-Tools CP-SAT implementation of the `Scheduler` interface.

    Job-shop-style model: one interval variable per work order, `AddNoOverlap`
    per work center, objective is total tardiness (`min_tardiness`, the
    schema default) or makespan (`min_makespan`). Same simplification
    `greedy_schedule` already makes - one work center per work order
    (`routing[0]`, default id `1`), `duration = ceil(qty / 10.0)` hours - so
    the two implementations are directly comparable on the same input.

    Falls back to the greedy result (labelled `cpsat_fallback_greedy`) if the
    solver does not reach a feasible solution within the time budget, rather
    than failing the request - the job is already async
    (`GET /api/v1/job/{id}`), so a slow solve does not block the caller
    either way.
    """

    name = "solver_cpsat"

    def __init__(self, time_limit_seconds: float = _TIME_LIMIT_SECONDS):
        self._time_limit_seconds = time_limit_seconds
        self._fallback = GreedyScheduler()

    def schedule(
        self,
        workorders: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        objective: str = "min_tardiness",
    ) -> Dict[str, Any]:
        if not workorders:
            return {
                "schedule_result": [],
                "kpi": {"makespan_hours": 0.0, "tardiness_hours": 0.0, "utilization": 0.0},
                "model": "cpsat_ortools",
            }

        origin = datetime.now().replace(minute=0, second=0, microsecond=0)
        durations: Dict[int, int] = {}
        workcenters: Dict[int, Any] = {}
        dues: Dict[int, int] = {}
        horizon_hours = _HORIZON_DAYS * 24

        for wo in workorders:
            wo_id = wo["workorder_id"]
            duration = max(math.ceil(float(wo.get("qty", 0.0)) / 10.0), 1)
            durations[wo_id] = duration
            workcenters[wo_id] = wo["routing"][0] if wo.get("routing") else 1
            due_hours = horizon_hours
            if wo.get("due"):
                try:
                    due_dt = datetime.fromisoformat(
                        wo["due"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    due_hours = max(int((due_dt - origin).total_seconds() // 3600), duration)
                except ValueError:
                    pass
            dues[wo_id] = due_hours

        # A due date past the default horizon must not make the model
        # infeasible - extend the horizon to cover the latest one.
        horizon_hours = max(horizon_hours, max(dues.values()) + max(durations.values()))

        model = cp_model.CpModel()
        starts: Dict[int, Any] = {}
        ends: Dict[int, Any] = {}
        by_workcenter: Dict[Any, List[Any]] = {}

        for wo in workorders:
            wo_id = wo["workorder_id"]
            duration = durations[wo_id]
            start = model.NewIntVar(0, horizon_hours, f"start_{wo_id}")
            end = model.NewIntVar(0, horizon_hours, f"end_{wo_id}")
            interval = model.NewIntervalVar(start, duration, end, f"interval_{wo_id}")
            starts[wo_id] = start
            ends[wo_id] = end
            by_workcenter.setdefault(workcenters[wo_id], []).append(interval)

        for intervals in by_workcenter.values():
            if len(intervals) > 1:
                model.AddNoOverlap(intervals)

        if objective == "min_makespan":
            makespan = model.NewIntVar(0, horizon_hours, "makespan")
            model.AddMaxEquality(makespan, list(ends.values()))
            model.Minimize(makespan)
        else:
            tardiness_vars = []
            for wo_id, end in ends.items():
                tardiness = model.NewIntVar(0, horizon_hours, f"tardiness_{wo_id}")
                model.Add(tardiness >= end - dues[wo_id])
                tardiness_vars.append(tardiness)
            model.Minimize(sum(tardiness_vars))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._time_limit_seconds
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            result = self._fallback.schedule(workorders, constraints, objective)
            result["model"] = "cpsat_fallback_greedy"
            return result

        schedule_result = []
        makespan_hours = 0.0
        tardiness_total = 0.0
        for wo in workorders:
            wo_id = wo["workorder_id"]
            start_h = solver.Value(starts[wo_id])
            end_h = solver.Value(ends[wo_id])
            delay = max(end_h - dues[wo_id], 0)
            tardiness_total += delay
            makespan_hours = max(makespan_hours, end_h - start_h)
            schedule_result.append({
                "workorder_id": wo_id,
                "workcenter_id": workcenters[wo_id],
                "date_start": (origin + timedelta(hours=start_h)).isoformat(),
                "date_finished": (origin + timedelta(hours=end_h)).isoformat(),
                "priority": wo.get("priority", 0),
                "conflict": False,
                "delay_hours": round(float(delay), 2),
                "score": round(1.0 / (1.0 + delay), 3),
            })

        busy_hours = sum(durations.values())
        span_hours = max((solver.Value(ends[wo_id]) for wo_id in ends), default=1) or 1
        utilization = min(busy_hours / (span_hours * max(len(by_workcenter), 1)), 1.0)

        kpi = {
            "makespan_hours": round(makespan_hours, 2),
            "tardiness_hours": round(tardiness_total, 2),
            "utilization": round(utilization, 2),
        }
        return {
            "schedule_result": schedule_result,
            "kpi": kpi,
            "model": "cpsat_ortools",
            "solver_status": solver.StatusName(status),
        }
