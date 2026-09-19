from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateState(str, Enum):
    CREATED = "CREATED"
    STATIC_REJECTED = "STATIC_REJECTED"
    STATIC_VALID = "STATIC_VALID"
    SIM_QUEUED = "SIM_QUEUED"
    SIM_RUNNING = "SIM_RUNNING"
    SIM_DONE = "SIM_DONE"
    QUALITY_REJECTED = "QUALITY_REJECTED"
    CORR_REJECTED = "CORR_REJECTED"
    SUBMIT_QUEUED = "SUBMIT_QUEUED"
    SUBMIT_PENDING = "SUBMIT_PENDING"
    ACTIVE = "ACTIVE"
    SUBMIT_REJECTED = "SUBMIT_REJECTED"
    RETRYABLE = "RETRYABLE"
    UNKNOWN = "UNKNOWN"


class Lane(str, Enum):
    REGULAR = "REGULAR"
    SUPER = "SUPER"


@dataclass(frozen=True)
class ResearchProfile:
    instrument_type: str
    region: str
    universe: str
    delay: int
    decay: int
    neutralization: str
    truncation: float
    pasteurization: str = "ON"
    unit_handling: str = "VERIFY"
    nan_handling: str = "OFF"
    language: str = "FASTEXPR"
    visualization: bool = False


@dataclass
class Metrics:
    sharpe: float | None = None
    fitness: float | None = None
    returns: float | None = None
    turnover: float | None = None
    drawdown: float | None = None
    margin: float | None = None
    sub_universe_sharpe: float | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_alpha(cls, alpha: dict[str, Any]) -> "Metrics":
        block = alpha.get("is") or {}
        checks = block.get("checks") or alpha.get("checks") or []
        sub = None
        for c in checks:
            if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE":
                sub = c.get("value")
                break
        return cls(
            sharpe=_num(block.get("sharpe")),
            fitness=_num(block.get("fitness")),
            returns=_num(block.get("returns")),
            turnover=_num(block.get("turnover")),
            drawdown=_num(block.get("drawdown")),
            margin=_num(block.get("margin")),
            sub_universe_sharpe=_num(sub),
            checks=checks,
        )


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class Candidate:
    id: str
    lane: Lane
    expression: str | None
    settings: dict[str, Any]
    state: CandidateState = CandidateState.CREATED
    fingerprint: str = ""
    parent_ids: list[str] = field(default_factory=list)
    hypothesis: str = ""
    family: str = "unknown"
    strategy_arm: str = "baseline"
    alpha_id: str | None = None
    simulation_id: str | None = None
    metrics: Metrics = field(default_factory=Metrics)
    corr_max: float | None = None
    reason: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_json(self) -> dict[str, Any]:
        x = asdict(self)
        x["created_at"] = self.created_at.isoformat()
        x["updated_at"] = self.updated_at.isoformat()
        x["state"] = self.state.value
        x["lane"] = self.lane.value
        return x
