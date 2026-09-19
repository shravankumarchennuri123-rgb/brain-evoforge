from __future__ import annotations

import math
import random
from typing import Any


class StrategyBandit:
    """Simple UCB-like policy over research strategy arms.

    It controls *which research mutation family to explore*, not safety gates.
    Safety thresholds and write permissions are never learned.
    """
    DEFAULT_ARMS = (
        "window_mutation", "operator_mutation", "normalization_mutation",
        "field_mutation", "crossover", "crossover_residual", "exploration_new_family"
    )

    def __init__(self, rows: list[dict[str, Any]], exploration: float = 1.25):
        self.exploration = exploration
        self.stats = {r["arm"]: r for r in rows}

    def select(self) -> str:
        unseen = [a for a in self.DEFAULT_ARMS if self.stats.get(a, {}).get("pulls", 0) == 0]
        if unseen:
            return random.choice(unseen)
        total = sum(max(1, int(v.get("pulls", 0))) for v in self.stats.values())
        best_arm = None
        best_score = -float("inf")
        for arm in self.DEFAULT_ARMS:
            r = self.stats.get(arm, {"pulls": 0, "reward_sum": 0.0})
            pulls = max(1, int(r.get("pulls", 0)))
            mean = float(r.get("reward_sum", 0.0)) / pulls
            score = mean + self.exploration * math.sqrt(math.log(total + 1) / pulls)
            if score > best_score:
                best_score, best_arm = score, arm
        return best_arm or self.DEFAULT_ARMS[0]
