from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import hashlib
from typing import Any, Iterable

from .genome import ExpressionSyntaxError, build_genome
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
    """Generate diverse, researchable cross-domain hypotheses without simulation.

    Design rules:
    - never pair a field with itself;
    - never emit the same field-pair/mechanism twice;
    - use canonical semantic domains to collapse aliases such as sentiment/text_nlp;
    - prefer multiple high-quality fields over repeatedly selecting the first field;
    - avoid generic cross-unit ratios;
    - measure novelty against the existing population, not as proof of future alpha quality.
    """

    _CANONICAL_TRAIT = {
        "text_nlp": "sentiment",
        "social_attention": "social_media",
        "institutional_positioning": "ownership",
        "earnings": "earnings",
        "expectation_revision": "analyst_expectations",
    }

    def __init__(self, fields: Iterable[dict[str, Any]], existing_expressions: Iterable[str] = ()):
        self.fields = [x for x in fields if str(x.get("id") or "")]
        self.existing_expressions = list(existing_expressions)
        self.existing_genomes = []
        self.unparsed_existing: list[str] = []
        for expression in self.existing_expressions:
            try:
                self.existing_genomes.append(build_genome(expression, self.fields))
            except ExpressionSyntaxError:
                self.unparsed_existing.append(expression)
        self._trait_index = self._build_trait_index()

    def _build_trait_index(self) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for row in self.fields:
            raw_traits = infer_field_traits(row)
            canonical = {
                self._CANONICAL_TRAIT.get(t, t)
                for t in raw_traits
            }
            for trait in canonical:
                index.setdefault(trait, []).append(row)

        for trait, rows in index.items():
            rows.sort(key=self._field_sort_key)
        return index

    @staticmethod
    def _field_sort_key(row: dict[str, Any]) -> tuple[float, float, float, str, str]:
        coverage = _float(row.get("coverage")) or 0.0
        date_coverage = _float(row.get("dateCoverage") or row.get("date_coverage")) or 0.0
        alpha_count = max(0.0, _float(row.get("alphaCount") or row.get("alpha_count")) or 0.0)
        text = " ".join(
            str(row.get(k) or "")
            for k in ("id", "category", "dataset", "description", "name")
        ).lower()
        # Metadata quality first; alphaCount is only a weak tie-breaker.
        return (-coverage, -date_coverage, alpha_count, text, str(row.get("id")))

    def _eligible_fields(self, trait: str, limit: int = 12) -> list[dict[str, Any]]:
        canonical = self._CANONICAL_TRAIT.get(trait, trait)
        rows = self._trait_index.get(canonical, [])
        return [x for x in rows if str(x.get("type") or "MATRIX").upper() == "MATRIX"][:limit]

    def _trait_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for genome in self.existing_genomes:
            canonical = {self._CANONICAL_TRAIT.get(t, t) for t in genome.semantic_traits}
            for trait in canonical:
                counts[trait] = counts.get(trait, 0) + 1
        return counts

    def _all_traits(self) -> list[str]:
        traits: set[str] = set()
        for row in self.fields:
            traits.update(self._CANONICAL_TRAIT.get(t, t) for t in infer_field_traits(row))
        return sorted(traits)

    @staticmethod
    def _pair_quality(a: dict[str, Any], b: dict[str, Any]) -> float:
        # Reward coverage and history alignment, but penalize the temptation to
        # use two nearly identical fields from the same dataset.
        ac = _float(a.get("coverage")) or 0.0
        ad = _float(a.get("dateCoverage") or a.get("date_coverage")) or 0.0
        bc = _float(b.get("coverage")) or 0.0
        bd = _float(b.get("dateCoverage") or b.get("date_coverage")) or 0.0
        same_dataset = str(a.get("dataset") or "") == str(b.get("dataset") or "")
        return 0.4 * min(ac, bc) + 0.4 * min(ad, bd) + (0.2 if not same_dataset else 0.0)

    def _field_pair_pool(
        self,
        trait_a: str,
        trait_b: str,
        *,
        per_trait: int = 8,
        max_pairs: int = 20,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        left = self._eligible_fields(trait_a, per_trait)
        right = self._eligible_fields(trait_b, per_trait)
        pairs: list[tuple[float, str, dict[str, Any], dict[str, Any]]] = []

        for a in left:
            for b in right:
                aid, bid = str(a["id"]), str(b["id"])
                if aid == bid:
                    continue
                # Avoid pretending two fields from the same dataset are a genuinely
                # cross-domain experiment unless no alternative pair exists later.
                score = self._pair_quality(a, b)
                key = f"{min(aid,bid)}|{max(aid,bid)}"
                pairs.append((score, key, a, b))

        pairs.sort(key=lambda x: (-x[0], x[1]))
        return [(a, b) for _, _, a, b in pairs[:max_pairs]]

    def _trait_exposure(self, trait: str) -> int:
        return self._trait_counts().get(trait, 0)

    def plan(self, n: int = 20) -> list[ResearchHypothesis]:
        if n <= 0 or not self.fields:
            return []

        traits = self._all_traits()
        # Low exposure gets priority, but every trait has to compete on actual
        # field availability and pair diversity.
        traits.sort(key=lambda t: (self._trait_exposure(t), t))

        hypotheses: list[ResearchHypothesis] = []
        seen_expressions: set[str] = set()
        seen_pairs: set[tuple[str, str, str]] = set()

        mechanisms = (
            (
                "cross_domain_interaction",
                "medium",
                lambda a, b: f"rank(ts_zscore({a},60)*ts_zscore({b},60))",
                lambda ta, tb: f"Test whether joint extremes in {ta} and {tb} contain information beyond either input alone.",
            ),
            (
                "cross_domain_spread",
                "medium",
                lambda a, b: f"rank(ts_zscore({a},60)-ts_zscore({b},60))",
                lambda ta, tb: f"Test whether relative disagreement between standardized {ta} and {tb} carries information.",
            ),
            (
                "cross_domain_co_movement",
                "medium",
                lambda a, b: f"rank(ts_corr(rank({a}),rank({b}),20))",
                lambda ta, tb: f"Test whether {ta} and {tb} co-move within securities over a 20-session horizon.",
            ),
        )

        # Round-robin across trait pairs and field pairs so the campaign explores
        # the research space instead of filling all 20 slots with one anchor field.
        for a_i, trait_a in enumerate(traits):
            for trait_b in traits[a_i + 1:]:
                if self._CANONICAL_TRAIT.get(trait_a, trait_a) == self._CANONICAL_TRAIT.get(trait_b, trait_b):
                    continue
                field_pairs = self._field_pair_pool(trait_a, trait_b)
                if not field_pairs:
                    continue

                for pair_i, (field_a, field_b) in enumerate(field_pairs):
                    aid, bid = str(field_a["id"]), str(field_b["id"])
                    for mech_i, (mechanism, horizon, expr_fn, rationale_fn) in enumerate(mechanisms):
                        key = (min(aid, bid), max(aid, bid), mechanism)
                        if key in seen_pairs:
                            continue
                        expr = expr_fn(aid, bid)
                        canonical_expr = "".join(expr.split())
                        if canonical_expr in seen_expressions:
                            continue

                        genome = build_genome(expr, self.fields)
                        nov = novelty_score(genome, self.existing_genomes).overall
                        hid = hashlib.sha1(
                            f"{trait_a}|{trait_b}|{mechanism}|{aid}|{bid}".encode()
                        ).hexdigest()[:12]
                        hypotheses.append(
                            ResearchHypothesis(
                                hypothesis_id=f"H-{hid}",
                                thesis=f"{trait_a} × {trait_b}",
                                mechanism=mechanism,
                                fields=(aid, bid),
                                traits=tuple(sorted((trait_a, trait_b))),
                                expression=expr,
                                expected_horizon=horizon,
                                rationale=rationale_fn(trait_a, trait_b),
                                novelty_prior=nov,
                            )
                        )
                        seen_pairs.add(key)
                        seen_expressions.add(canonical_expr)
                        if len(hypotheses) >= n * 4:
                            break
                    if len(hypotheses) >= n * 4:
                        break
                if len(hypotheses) >= n * 4:
                    break
            if len(hypotheses) >= n * 4:
                break

        # First-order ranking by novelty, then deterministic diversity by field pair
        # and mechanism. The output itself is a campaign shortlist, not a submission rank.
        hypotheses.sort(
            key=lambda h: (
                -h.novelty_prior,
                h.mechanism,
                h.traits,
                h.fields,
                h.hypothesis_id,
            )
        )

        selected: list[ResearchHypothesis] = []
        seen_trait_pairs: set[tuple[str, str]] = set()
        seen_field_ids: set[str] = set()
        seen_mechanisms: set[str] = set()

        # Greedy diversity pass: choose high-novelty hypotheses while preventing the
        # exact concentration problem observed in the first 20-hypothesis output.
        for h in hypotheses:
            pair = tuple(h.traits)
            novelty_bonus = (
                (1 if pair not in seen_trait_pairs else 0)
                + (1 if h.mechanism not in seen_mechanisms else 0)
                + (1 if not (set(h.fields) & seen_field_ids) else 0)
            )
            if novelty_bonus > 0 or len(selected) < max(1, n // 3):
                selected.append(h)
                seen_trait_pairs.add(pair)
                seen_mechanisms.add(h.mechanism)
                seen_field_ids.update(h.fields)
            if len(selected) >= n:
                break

        return selected


def _float(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None
