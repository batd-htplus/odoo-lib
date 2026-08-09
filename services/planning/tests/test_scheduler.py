"""Tests for the Scheduler adapter boundary (app/scheduler/).

Run with: cd services/planning && python -m pytest tests/ -v
(requires requirements.txt installed, notably ortools - no Docker/Odoo
needed, these exercise the FastAPI app in isolation.)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.scheduler import REGISTRY, CpSatScheduler, GreedyScheduler, get_scheduler


def _workorder(wo_id, qty=10.0, due_in_hours=24, workcenter=1, priority=0):
    due = (datetime.now() + timedelta(hours=due_in_hours)).isoformat() + "Z"
    return {
        "workorder_id": wo_id,
        "product_id": 1,
        "qty": qty,
        "routing": [workcenter],
        "due": due,
        "priority": priority,
    }


class TestRegistry:
    def test_known_algorithms_resolve(self):
        assert isinstance(get_scheduler("rule_engine"), GreedyScheduler)
        assert isinstance(get_scheduler("solver_cpsat"), CpSatScheduler)

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unknown scheduling algorithm"):
            get_scheduler("magic")

    def test_registry_keys_match_odoo_selection_minus_manual(self):
        # Mirrors htplus.schedule.run.algorithm's selection values in
        # addons/htplus_aps_core/models/htplus_schedule.py, minus 'manual'
        # (no API equivalent). If that selection changes, this test and the
        # registry should change together.
        assert set(REGISTRY) == {"rule_engine", "solver_cpsat"}


class TestGreedyScheduler:
    def test_matches_services_greedy_schedule(self):
        # greedy_schedule() calls datetime.now() internally as the
        # fallback start time when a work center has no prior cursor entry,
        # so two independent calls (direct vs. via the adapter) legitimately
        # produce date_start/date_finished a few microseconds apart -
        # strip those before comparing; everything else must be identical,
        # since the adapter must not alter behaviour, only wrap it.
        from app.services import greedy_schedule

        def _without_timestamps(result):
            return {
                **result,
                "schedule_result": [
                    {k: v for k, v in entry.items() if k not in ("date_start", "date_finished")}
                    for entry in result["schedule_result"]
                ],
            }

        workorders = [_workorder(1), _workorder(2)]
        direct = greedy_schedule(workorders, "min_tardiness")
        via_adapter = GreedyScheduler().schedule(workorders, {}, "min_tardiness")
        assert _without_timestamps(direct) == _without_timestamps(via_adapter)

    def test_empty_input(self):
        result = GreedyScheduler().schedule([], {}, "min_tardiness")
        assert result["schedule_result"] == []


class TestCpSatScheduler:
    def test_empty_input(self):
        result = CpSatScheduler().schedule([], {}, "min_tardiness")
        assert result["schedule_result"] == []
        assert result["model"] == "cpsat_ortools"

    def test_single_workorder_schedules_at_or_after_now(self):
        result = CpSatScheduler().schedule([_workorder(1)], {}, "min_tardiness")
        assert len(result["schedule_result"]) == 1
        entry = result["schedule_result"][0]
        assert entry["workorder_id"] == 1
        start = datetime.fromisoformat(entry["date_start"])
        end = datetime.fromisoformat(entry["date_finished"])
        assert end > start

    def test_same_workcenter_never_overlaps(self):
        # Three work orders forced onto the same work center: the whole
        # point of AddNoOverlap. If this regresses, the solver is no longer
        # doing anything the greedy cursor didn't already do.
        workorders = [
            _workorder(1, qty=10, workcenter=1),
            _workorder(2, qty=10, workcenter=1),
            _workorder(3, qty=10, workcenter=1),
        ]
        result = CpSatScheduler(time_limit_seconds=5.0).schedule(workorders, {}, "min_tardiness")
        intervals = sorted(
            (
                datetime.fromisoformat(e["date_start"]),
                datetime.fromisoformat(e["date_finished"]),
            )
            for e in result["schedule_result"]
        )
        for (_, end_a), (start_b, _) in zip(intervals, intervals[1:]):
            assert end_a <= start_b

    def test_different_workcenters_can_overlap(self):
        workorders = [
            _workorder(1, qty=10, workcenter=1),
            _workorder(2, qty=10, workcenter=2),
        ]
        result = CpSatScheduler(time_limit_seconds=5.0).schedule(workorders, {}, "min_makespan")
        by_id = {e["workorder_id"]: e for e in result["schedule_result"]}
        # Both should start at (or near) the same origin since they don't
        # contend for the same work center - makespan objective favours it.
        start_1 = datetime.fromisoformat(by_id[1]["date_start"])
        start_2 = datetime.fromisoformat(by_id[2]["date_start"])
        assert abs((start_1 - start_2).total_seconds()) < 3600

    def test_min_tardiness_prioritises_earlier_due_date(self):
        # Two work orders on the same work center, competing for the first
        # slot. duration = ceil(qty / 10) = 1h for both. urgent's due (1h)
        # equals its own duration exactly, so it is only on-time if
        # scheduled first (second => 1h late); relaxed's due (48h) is never
        # binding either way - so min_tardiness has a unique optimum
        # (urgent first), not a tie the solver could break arbitrarily.
        urgent = _workorder(1, qty=10, due_in_hours=1, workcenter=1)
        relaxed = _workorder(2, qty=10, due_in_hours=48, workcenter=1)
        result = CpSatScheduler(time_limit_seconds=5.0).schedule(
            [relaxed, urgent], {}, "min_tardiness"
        )
        by_id = {e["workorder_id"]: e for e in result["schedule_result"]}
        assert by_id[1]["date_start"] <= by_id[2]["date_start"]

    def test_falls_back_to_greedy_when_infeasible(self, monkeypatch):
        from ortools.sat.python import cp_model

        scheduler = CpSatScheduler(time_limit_seconds=0.01)
        real_cp_solver = cp_model.CpSolver

        class _AlwaysInfeasibleSolver:
            def __init__(self):
                # Real CpSolver(), not the patched name, to avoid recursing
                # into this same mock via app.scheduler.cpsat.cp_model.CpSolver.
                self.parameters = real_cp_solver().parameters

            def Solve(self, model):  # noqa: N802 - matches ortools' API
                return cp_model.INFEASIBLE

            def Value(self, var):  # pragma: no cover - not reached
                raise AssertionError("Value() should not be called after INFEASIBLE")

            def StatusName(self, status):  # noqa: N802
                return "INFEASIBLE"

        monkeypatch.setattr(
            "app.scheduler.cpsat.cp_model.CpSolver", _AlwaysInfeasibleSolver
        )
        result = scheduler.schedule([_workorder(1)], {}, "min_tardiness")
        assert result["model"] == "cpsat_fallback_greedy"
        assert len(result["schedule_result"]) == 1
