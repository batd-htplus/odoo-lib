from __future__ import annotations

from typing import Any, Dict, List

from ..services import greedy_schedule


class GreedyScheduler:
    """Adapts `services.greedy_schedule` to the `Scheduler` interface.

    Deliberately a thin wrapper, not a reimplementation: `services.py` is
    the module tests and any direct caller already import, and duplicating
    its body here would be exactly the kind of drift this adapter boundary
    exists to prevent. `constraints` is accepted (to match the interface)
    and ignored, same as `greedy_schedule` itself always has.
    """

    name = "rule_engine"

    def schedule(
        self,
        workorders: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        objective: str = "min_tardiness",
    ) -> Dict[str, Any]:
        return greedy_schedule(workorders, objective)
