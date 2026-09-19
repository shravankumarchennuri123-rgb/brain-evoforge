from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .genome import AlphaGenome, build_genome


@dataclass(frozen=True)
class NoveltyBreakdown:
    semantic_novelty: float
    field_novelty: float
    operator_novelty: float
    structure_novelty: float
    settings_novelty: float
    overall: float
    nearest_similarity: float

    def to_dict(self) -> dict[str, float]:
        return {
            "semantic_novelty": self.semantic_novelty,
            "field_novelty": self.field_novelty,
            "operator_novelty": self.operator_novelty,
            "structure_novelty": self.structure_novelty,
            "settings_novelty": self.settings_novelty,
            "overall": self.overall,
            "nearest_similarity": self.nearest_similarity,
        }


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def genome_similarity(a: AlphaGenome, b: AlphaGenome) -> dict[str, float]:
    """Semantic/structural similarity used before expensive correlation endpoints.

    This is not a replacement for realized PnL correlation or BRAIN's own
    correlation checks. It is a cheap research-space redundancy measure.
    """
    return {
        "semantic": _jaccard(a.semantic_traits, b.semantic_traits),
        "fields": _jaccard((x.field_id for x in a.fields), (x.field_id for x in b.fields)),
        "operators": _jaccard(a.operators, b.operators),
        "structure": 1.0 if a.ast_signature == b.ast_signature else 0.0,
        "datasets": _jaccard(a.datasets, b.datasets),
    }


def novelty_score(
    genome: AlphaGenome,
    existing: Iterable[AlphaGenome],
    *,
    settings: dict[str, Any] | None = None,
    existing_settings: Iterable[dict[str, Any]] = (),
) -> NoveltyBreakdown:
    """Score research-space novelty against a known alpha population.

    Higher values mean less redundancy. The weights are deliberately exposed
    here rather than hidden inside the submission gate, because novelty is a
    research heuristic and must not masquerade as a platform rule.
    """
    population = list(existing)
    if not population:
        return NoveltyBreakdown(1.0, 1.0, 1.0, 1.0, 1.0 if settings is not None else 0.0, 1.0, 0.0)

    similarities: list[tuple[float, dict[str, float]]] = []
    for other in population:
        parts = genome_similarity(genome, other)
        # Semantic similarity matters most; exact structural overlap is a strong
        # duplicate signal. Dataset overlap is a weaker redundancy signal.
        sim = (
            0.35 * parts["semantic"]
            + 0.25 * parts["fields"]
            + 0.15 * parts["operators"]
            + 0.15 * parts["structure"]
            + 0.10 * parts["datasets"]
        )
        similarities.append((sim, parts))

    nearest, nearest_parts = max(similarities, key=lambda x: x[0])

    settings_novelty = 0.0
    if settings is not None:
        known = list(existing_settings)
        if known:
            def equal_ratio(other: dict[str, Any]) -> float:
                keys = set(settings) | set(other)
                if not keys:
                    return 1.0
                return sum(settings.get(k) == other.get(k) for k in keys) / len(keys)
            settings_novelty = 1.0 - max(equal_ratio(x) for x in known)

    semantic_novelty = 1.0 - nearest_parts["semantic"]
    field_novelty = 1.0 - nearest_parts["fields"]
    operator_novelty = 1.0 - nearest_parts["operators"]
    structure_novelty = 1.0 - nearest_parts["structure"]

    overall = (
        0.35 * semantic_novelty
        + 0.25 * field_novelty
        + 0.15 * operator_novelty
        + 0.15 * structure_novelty
        + 0.10 * settings_novelty
    )
    return NoveltyBreakdown(
        semantic_novelty=semantic_novelty,
        field_novelty=field_novelty,
        operator_novelty=operator_novelty,
        structure_novelty=structure_novelty,
        settings_novelty=settings_novelty,
        overall=overall,
        nearest_similarity=nearest,
    )


def build_and_score(
    expression: str,
    field_catalog: Iterable[dict[str, Any]],
    existing_expressions: Iterable[str],
    *,
    settings: dict[str, Any] | None = None,
    existing_settings: Iterable[dict[str, Any]] = (),
) -> tuple[AlphaGenome, NoveltyBreakdown]:
    genome = build_genome(expression, field_catalog)
    existing_genomes = [build_genome(x, field_catalog) for x in existing_expressions]
    score = novelty_score(
        genome,
        existing_genomes,
        settings=settings,
        existing_settings=existing_settings,
    )
    return genome, score
