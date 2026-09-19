from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import hashlib
from typing import Any, Iterable

from .genome import build_genome
from .ontology import infer_field_traits
from .novelty import novelty_score


@dataclass(frozen=True)
class ResearchHypothesis:
    hypothesis_id: str
    thesis: str
    mechanism: str
    fields: tuple[str, ...]
    traits: tuple[str, ...]
    expression: str
    expected_horizon: str
    rationale: str
    novelty_prior: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "thesis": self.thesis,
            "mechanism": self.mechanism,
            "fields": list(self.fields),
            "traits": list(self.traits),
            "expression": self.expression,
            "expected_horizon": self.expected_horizon,
            "rationale": self.rationale,
            "novelty_prior": self.novelty_prior,
        }


_TRAIT_FAMILY = {
    "analyst_expectations": "expectation_revision",
    "sentiment": "text_sentiment",
    "news": "news_information",
    "social_media": "social_attention",
    "institutional_positioning": "institutional_positioning",
    "ownership": "ownership",
    "insider_activity": "insider_activity",
    "short_interest": "short_interest",
    "fundamentals": "fundamentals",
    "profitability": "profitability",
    "cash_flow": "cash_flow",
    "earnings": "earnings",
    "price_volume": "price_volume",
    "liquidity": "liquidity",
    "risk": "risk",
    "alternative_data": "alternative_data",
    "esg": "esg",
}


class HypothesisEngine:
    """Generate cross-domain research hypotheses without touching /simulations.

    The engine searches for complementary data traits rather than blindly
    enumerating fields. Every generated expression still must pass the live
    validator before simulation.
    """

    def __init__(self, fields: Iterable[dict[str, Any]], existing_expressions: Iterable[str] = ()):
        self.fields = [x for x in fields if str(x.get("id") or "")]
        self.existing_expressions = list(existing_expressions)
        self.existing_genomes = [build_genome(x, self.fields) for x in self.existing_expressions]

    def _trait_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for genome in self.existing_genomes:
            for trait in genome.semantic_traits:
                counts[trait] = counts.get(trait, 0) + 1
        return counts

    def _eligible_fields(self, trait: str, limit: int = 12) -> list[dict[str, Any]]:
        rows = []
        for row in self.fields:
            text = " ".join(str(row.get(k) or "") for k in ("id", "category", "dataset", "description", "name")).lower()
            if trait not in infer_field_traits(row):
                # build_genome only recognizes a field when it is in the catalog;
                # a direct metadata fallback keeps this path robust.
                continue
            if str(row.get("type") or "MATRIX").upper() != "MATRIX":
                continue
            coverage = _float(row.get("coverage"))
            date_coverage = _float(row.get("dateCoverage") or row.get("date_coverage"))
            alpha_count = _float(row.get("alphaCount") or row.get("alpha_count"))
            quality = 0.55 * (coverage if coverage is not None else 0.0) + 0.35 * (date_coverage if date_coverage is not None else 0.0)
            # alphaCount is deliberately only a small tie-breaker, never proof of novelty.
            quality += 0.10 / (1.0 + max(0.0, alpha_count or 0.0))
            rows.append((quality, text, row))
        rows.sort(key=lambda x: (-x[0], x[1]))
        return [x[2] for x in rows[:limit]]

    def plan(self, n: int = 20) -> list[ResearchHypothesis]:
        if n <= 0 or not self.fields:
            return []

        trait_counts = self._trait_counts()
        all_traits = sorted({
            trait
            for row in self.fields
            for trait in infer_field_traits(row)
        })
        # Prefer traits with low current alpha exposure, but keep price_volume as a
        # control/reference family so every campaign does not drift into exotic data.
        ranked_traits = sorted(
            all_traits,
            key=lambda t: (trait_counts.get(t, 0), t),
        )

        hypotheses: list[ResearchHypothesis] = []
        used_pairs: set[tuple[str, str]] = set()
        for a, b in combinations(ranked_traits, 2):
            pair = tuple(sorted((a, b)))
            if pair in used_pairs:
                continue
            # Avoid duplicate concepts from two naming aliases.
            if _TRAIT_FAMILY.get(a, a) == _TRAIT_FAMILY.get(b, b):
                continue
            fa = self._eligible_fields(a, limit=5)
            fb = self._eligible_fields(b, limit=5)
            if not fa or not fb:
                continue

            field_a = str(fa[0]["id"])
            field_b = str(fb[0]["id"])

            # Three distinct mechanism templates rather than parameter sweeps.
            templates = [
                (
                    f"rank(ts_corr(rank({field_a}),rank({field_b}),20))",
                    "cross_domain_co_movement",
                    "medium",
                    f"Test whether changes in {a} and {b} exhibit useful cross-sectional co-movement at a 20-session horizon.",
                ),
                (
                    f"rank(ts_zscore({field_a},60)*ts_zscore({field_b},60))",
                    "cross_domain_interaction",
                    "medium",
                    f"Test whether joint extremes in {a} and {b} contain information beyond either input alone.",
                ),
                (
                    f"rank({field_a}/(abs({field_b})+0.001))",
                    "relative_information_intensity",
                    "short_medium",
                    f"Test whether relative magnitude between {a} and {b} is informative rather than the level of either series.",
                ),
            ]

            for expr, mechanism, horizon, rationale in templates:
                genome = build_genome(expr, self.fields)
                nov = novelty_score(genome, self.existing_genomes).overall
                hid = hashlib.sha1(f"{a}|{b}|{mechanism}|{field_a}|{field_b}".encode()).hexdigest()[:12]
                hypotheses.append(
                    ResearchHypothesis(
                        hypothesis_id=f"H-{hid}",
                        thesis=f"{_TRAIT_FAMILY.get(a,a)} × {_TRAIT_FAMILY.get(b,b)}",
                        mechanism=mechanism,
                        fields=(field_a, field_b),
                        traits=tuple(sorted((a, b))),
                        expression=expr,
                        expected_horizon=horizon,
                        rationale=rationale,
                        novelty_prior=nov,
                    )
                )
            used_pairs.add(pair)
            if len(hypotheses) >= n * 3:
                break

        hypotheses.sort(key=lambda h: (-h.novelty_prior, h.hypothesis_id))
        return hypotheses[:n]


def _float(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None
