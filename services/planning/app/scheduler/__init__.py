from __future__ import annotations

from typing import Dict

from .base import Scheduler
from .cpsat import CpSatScheduler
from .greedy import GreedyScheduler

REGISTRY: Dict[str, Scheduler] = {
    "rule_engine": GreedyScheduler(),
    "solver_cpsat": CpSatScheduler(),
}


def get_scheduler(algorithm: str) -> Scheduler:
    try:
        return REGISTRY[algorithm]
    except KeyError:
        raise ValueError(
            f"Unknown scheduling algorithm {algorithm!r}. Available: {sorted(REGISTRY)}"
        ) from None


__all__ = ["Scheduler", "GreedyScheduler", "CpSatScheduler", "REGISTRY", "get_scheduler"]
