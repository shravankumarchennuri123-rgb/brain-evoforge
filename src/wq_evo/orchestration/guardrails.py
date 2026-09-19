from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..models import Metrics


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reasons: tuple[str, ...]


class SubmissionGuard:
    """Deterministic gates. Never self-modified by the learning system."""

    def __init__(self, *, write_armed: bool, allow_unknown_budget: bool):
        self.write_armed = write_armed
        self.allow_unknown_budget = allow_unknown_budget

    def prewrite(self, *, budget_known: bool, budget_remaining: int | None, target_remaining: int,
                 check_results: list[dict[str, Any]], corr_max: float | None,
                 metrics: Metrics, require_corr: bool = True, corr_limit: float = 0.7) -> GateDecision:
        reasons: list[str] = []
        if not self.write_armed:
            reasons.append("writes are disarmed")
        if target_remaining <= 0:
            reasons.append("target already complete")
        if not budget_known and not self.allow_unknown_budget:
            reasons.append("submission budget is not known")
        if budget_known and budget_remaining is not None and budget_remaining <= 0:
            reasons.append("platform budget exhausted")
        if any(str(c.get("result", "")).upper() == "FAIL" for c in check_results):
            reasons.append("one or more platform checks failed")
        if metrics.sharpe is None or metrics.fitness is None or metrics.turnover is None:
            reasons.append("required metrics are missing")
        if require_corr and corr_max is None:
            reasons.append("correlation verdict is missing")
        if corr_max is not None and abs(float(corr_max)) >= float(corr_limit):
            reasons.append("self-correlation gate is not passed")
        return GateDecision(not reasons, tuple(reasons))


def env_bool(name: str, default: bool = False) -> bool:
    return str(os.getenv(name, str(default))).lower() in {"1", "true", "yes", "on"}
