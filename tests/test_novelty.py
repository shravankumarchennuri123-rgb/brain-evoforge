from wq_evo.research.genome import build_genome
from wq_evo.research.novelty import genome_similarity, novelty_score


CATALOG = [
    {"id": "sent_a", "category": "Sentiment", "dataset": "News"},
    {"id": "sent_b", "category": "Sentiment", "dataset": "News"},
    {"id": "own_a", "category": "Institutions", "dataset": "Ownership"},
]


def test_exact_structure_is_not_novel():
    a = build_genome("rank(ts_delta(sent_a,5))", CATALOG)
    b = build_genome("rank(ts_delta(sent_a,5))", CATALOG)
    x = novelty_score(a, [b])
    assert x.overall == 0.0
    assert x.nearest_similarity == 1.0


def test_new_field_is_more_novel():
    a = build_genome("rank(ts_delta(own_a,5))", CATALOG)
    b = build_genome("rank(ts_delta(sent_a,5))", CATALOG)
    parts = genome_similarity(a, b)
    assert parts["semantic"] == 0.0
    assert parts["fields"] == 0.0


def test_empty_population_is_maximally_novel():
    a = build_genome("rank(sent_a)", CATALOG)
    x = novelty_score(a, [])
    assert x.overall == 1.0
