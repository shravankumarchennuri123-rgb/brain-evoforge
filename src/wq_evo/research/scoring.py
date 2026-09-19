from __future__ import annotations

from ..models import Metrics


def reward(metrics: Metrics, corr_max: float | None, accepted: bool) -> float:
    """Bounded reward for policy learning; never used as a submission gate."""
    components: list[float] = []
    if metrics.fitness is not None:
        components.append(max(-1.0, min(1.0, metrics.fitness / 3.0)))
    if metrics.sharpe is not None:
        components.append(max(-1.0, min(1.0, metrics.sharpe / 3.0)))
    if metrics.turnover is not None:
        components.append(max(-1.0, min(1.0, 0.5 - metrics.turnover)))
    if corr_max is not None:
        components.append(max(-1.0, min(1.0, 0.7 - abs(corr_max))))
    components.append(1.0 if accepted else -0.2 if metrics.fitness is not None else -1.0)
    return sum(components) / len(components)
