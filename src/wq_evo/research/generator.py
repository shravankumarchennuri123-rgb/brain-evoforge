from __future__ import annotations

import random
from typing import Any, Sequence

from .mutator import Mutation, mutate_expression


# These seeds are intentionally limited to operators observed in the live
# operator discovery. The orchestrator must still validate every candidate
# against the current live schema before simulation.
PORTABLE_SEEDS = [
    ("rank((close-open)/(high-low+0.001))", "price_intraday", "Range-normalized intraday direction."),
    ("rank(ts_delta(close,5)/ts_delay(close,5))", "price_momentum", "Short-horizon price change relative to a lagged reference."),
    ("rank(close/ts_mean(close,20))", "price_deviation", "Mean-reversion around a moving reference."),
    ("rank(ts_corr(rank(close),rank(volume),10))", "price_volume", "Cross-series co-movement."),
]


class CandidateGenerator:
    def __init__(self, operators: Sequence[dict[str, Any]], fields: Sequence[dict[str, Any]]):
        self.operator_names = [str(x.get("name") or x.get("id") or "") for x in operators]
        self.fields = [str(x.get("id")) for x in fields if x.get("id")]

    def initial(self, n: int = 12) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        for expr, family, hyp in PORTABLE_SEEDS:
            rows.append((expr, family, hyp, "seed"))
        # Add field-driven simple ratios only when the live catalog makes them plausible.
        useful = [
            f for f in self.fields
            if any(
                k in f.lower()
                for k in ("operating_income", "free_cash_flow", "est_eps", "sales", "assets", "equity")
            )
        ]
        random.shuffle(useful)
        for f in useful[: max(0, n - len(rows))]:
            rows.append((f"rank({f})", "live_field", f"Test the cross-sectional information in {f}.", "field_seed"))
        return rows[:n]

    def mutations(self, parents: list[tuple[str, str]]) -> list[Mutation]:
        out: list[Mutation] = []
        sibling_expr = parents[1][0] if len(parents) > 1 else None
        for expr, pid in parents[:4]:
            out.extend(mutate_expression(expr, candidate_id=pid, sibling=sibling_expr, fields=self.fields[:40]))
        return out
