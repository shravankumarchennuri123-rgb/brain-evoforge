from __future__ import annotations

import re
import random
from dataclasses import dataclass
from typing import Sequence


WINDOWS = (3, 5, 10, 20, 42, 63, 126, 252)
REPLACEMENTS = {
    "ts_mean": ("ts_sum", "ts_rank", "decay_linear"),
    "ts_sum": ("ts_mean", "ts_rank"),
    "ts_delta": ("ts_rank", "ts_shift"),
    "ts_rank": ("ts_mean", "ts_delta"),
    "rank": ("zscore", "scale"),
    "zscore": ("rank", "scale"),
    "decay_linear": ("ts_mean", "ts_rank"),
}


@dataclass(frozen=True)
class Mutation:
    expression: str
    strategy: str
    parent_ids: tuple[str, ...] = ()
    hypothesis: str = ""


def mutate_expression(expr: str, *, candidate_id: str, sibling: str | None = None,
                      fields: Sequence[str] = ()) -> list[Mutation]:
    out: list[Mutation] = []
    # 1. Numeric-window mutation, preserving the rest of the hypothesis.
    nums = list(re.finditer(r"(?<=,)(\d{1,3})(?=\))", expr))
    if nums:
        m = random.choice(nums)
        current = int(m.group(1))
        choices = [w for w in WINDOWS if w != current]
        new = random.choice(choices)
        out.append(Mutation(expr[:m.start()] + str(new) + expr[m.end():], "window_mutation", (candidate_id,),
                             f"Test a different temporal horizon ({new}) while holding the rest fixed."))

    # 2. Operator mutation.
    for op, repls in REPLACEMENTS.items():
        if op in expr:
            repl = random.choice(repls)
            out.append(Mutation(expr.replace(op, repl, 1), "operator_mutation", (candidate_id,),
                                f"Swap {op} for {repl} to test temporal aggregation sensitivity."))
            break

    # 3. Normalization mutation.
    if "rank(" not in expr and expr.count("(") < 8:
        out.append(Mutation(f"rank({expr})", "normalization_mutation", (candidate_id,),
                            "Apply cross-sectional ranking to suppress scale and outlier effects."))
    elif expr.startswith("rank("):
        out.append(Mutation(expr[5:-1], "simplify_normalization", (candidate_id,),
                            "Remove an outer rank to test whether normalization is destroying signal amplitude."))

    # 4. Field replacement from same discovery pool.
    if fields:
        field_hits = [f for f in fields if re.search(rf"(?<![A-Za-z0-9_]){re.escape(f)}(?![A-Za-z0-9_])", expr)]
        if field_hits:
            old = random.choice(field_hits)
            new_choices = [f for f in fields if f != old]
            if new_choices:
                new = random.choice(new_choices)
                out.append(Mutation(expr.replace(old, new, 1), "field_mutation", (candidate_id,),
                                    f"Swap {old} for {new} within the live field universe."))

    # 5. Crossover is only attempted when a sibling exists.
    if sibling:
        out.append(Mutation(f"0.5*({expr}) + 0.5*({sibling})", "crossover", (candidate_id,),
                            "Blend two distinct signal structures and test whether risk-adjusted quality improves."))
        out.append(Mutation(f"0.5*({expr}) - 0.5*({sibling})", "crossover_residual", (candidate_id,),
                            "Use a residual spread between two signals to seek orthogonal information."))

    # De-duplicate.
    seen: set[str] = set()
    unique: list[Mutation] = []
    for m in out:
        key = re.sub(r"\s+", "", m.expression)
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique[:8]
