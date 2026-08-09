from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class Scheduler(Protocol):

    def schedule(
        self,
        workorders: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        objective: str,
    ) -> Dict[str, Any]:
        """Return {"schedule_result": [...], "kpi": {...}, "model": "..."}.

        `schedule_result` entries and `kpi` keys follow the shape
        `services.greedy_schedule` already returns (see services.py) -
        every implementation in this package must match it, since Odoo's
        `htplus.planning.service.schedule_recommend()` parses the response
        without knowing which algorithm produced it.
        """
        ...
