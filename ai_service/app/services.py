from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


def moving_average_forecast(
    product_ids: List[int],
    history: List[Dict[str, Any]],
    horizon_days: int,
) -> Dict[str, Any]:
    per_product: Dict[int, List[float]] = {pid: [] for pid in product_ids}
    for item in history:
        qty = float(item.get("qty", 0.0))
        if qty > 0:
            per_product.setdefault(int(item["product_id"]), []).append(qty)

    lines = []
    start = datetime.now().date()
    for pid in product_ids:
        values = per_product.get(pid, [])
        base = sum(values) / len(values) if values else 0.0
        for day in range(horizon_days):
            date = start + timedelta(days=day)
            lines.append({
                "product_id": pid,
                "date": date.isoformat(),
                "qty": round(base, 2),
                "confidence": 0.5 if values else 0.1,
            })
    return {"lines": lines, "model": "moving_average_fallback"}


def greedy_schedule(workorders: List[Dict[str, Any]], objective: str = "min_tardiness") -> Dict[str, Any]:
    ordered = sorted(
        workorders,
        key=lambda w: (w.get("due") or "9999-12-31T00:00:00Z", -int(w.get("priority", 0))),
    )
    cursor: Dict[int, datetime] = {}
    result: List[Dict[str, Any]] = []
    makespan = 0.0
    tardiness = 0.0
    for wo in ordered:
        workcenter_id = wo["routing"][0] if wo.get("routing") else 1
        start = cursor.get(workcenter_id, datetime.now())
        duration = float(wo.get("qty", 0.0)) / 10.0
        end = start + timedelta(hours=max(duration, 0.5))
        cursor[workcenter_id] = end
        delay = 0.0
        if wo.get("due"):
            try:
                due = datetime.fromisoformat(wo["due"].replace("Z", "+00:00"))
                delay = max((end - due).total_seconds() / 3600.0, 0.0)
                tardiness += delay
            except ValueError:
                pass
        makespan = max(makespan, (end - start).total_seconds() / 3600.0)
        result.append({
            "workorder_id": wo["workorder_id"],
            "workcenter_id": workcenter_id,
            "schedule_start": start.isoformat(),
            "schedule_end": end.isoformat(),
            "priority": wo.get("priority", 0),
            "conflict": False,
            "delay_hours": round(delay, 2),
            "score": round(1.0 / (1.0 + delay), 3),
        })
    kpi = {
        "makespan_hours": round(makespan, 2),
        "tardiness_hours": round(tardiness, 2),
        "utilization": round(0.75, 2),
    }
    return {"schedule_result": result, "kpi": kpi, "model": "greedy_fallback"}


def heuristic_assignment(
    workorders: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    skill_matrix: Dict[int, List[int]],
) -> List[Dict[str, Any]]:
    result = []
    for wo in workorders:
        required = skill_matrix.get(wo["product_id"], [])
        best = None
        best_score = -1.0
        for emp in employees:
            skill_ok = all(s in emp["skills"] for s in required)
            score = float(skill_ok) * 10.0 - float(len(result))
            if score > best_score:
                best_score = score
                best = emp
        if best:
            result.append({
                "workorder_id": wo["workorder_id"],
                "employee_id": best["employee_id"],
                "score": round(best_score, 2),
                "skill_ok": all(s in best["skills"] for s in required),
                "ot_ok": True,
                "shift_conflict": False,
                "reason": "matched skill matrix" if best["skills"] else "fallback assignment",
            })
    return result


def rule_based_root_cause(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    causes = {}
    for item in history:
        factor = item.get("factor", "other")
        causes[factor] = causes.get(factor, 0) + 1
    total = sum(causes.values()) or 1
    return [
        {"factor": factor, "weight": round(count / total, 3), "evidence": history[:5]}
        for factor, count in sorted(causes.items(), key=lambda kv: -kv[1])
    ]
