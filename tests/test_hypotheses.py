from wq_evo.research.hypotheses import HypothesisEngine


FIELDS = [
    {"id": "sentiment_a", "category": "Sentiment", "dataset": "News", "type": "MATRIX", "coverage": 1, "dateCoverage": 1},
    {"id": "sentiment_b", "category": "Sentiment", "dataset": "Social", "type": "MATRIX", "coverage": 1, "dateCoverage": 1},
    {"id": "ownership_a", "category": "Institutions", "dataset": "Ownership", "type": "MATRIX", "coverage": 1, "dateCoverage": 1},
    {"id": "price_a", "category": "Price Volume", "dataset": "Prices", "type": "MATRIX", "coverage": 1, "dateCoverage": 1},
]


def test_hypothesis_engine_crosses_traits_without_simulation():
    hs = HypothesisEngine(FIELDS, existing_expressions=["rank(ts_delta(price_a,5))"]).plan(9)
    assert hs
    assert all(h.expression for h in hs)
    assert any(len(h.traits) == 2 for h in hs)
    assert all(h.novelty_prior >= 0 for h in hs)


def test_plan_is_deterministic_for_same_inputs():
    a = [h.to_dict() for h in HypothesisEngine(FIELDS).plan(6)]
    b = [h.to_dict() for h in HypothesisEngine(FIELDS).plan(6)]
    assert a == b


def test_non_code_existing_record_is_ignored():
    engine = HypothesisEngine(
        FIELDS,
        existing_expressions=[
            "rank(ts_delta(price_a,5))",
            "If the stock price moved sharply, this is explanatory text.",
        ],
    )
    assert len(engine.existing_genomes) == 1
    assert len(engine.unparsed_existing) == 1


def test_no_hypothesis_uses_same_field_twice():
    hs = HypothesisEngine(FIELDS).plan(30)
    assert hs
    assert all(h.fields[0] != h.fields[1] for h in hs)


def test_no_generic_cross_unit_ratio_is_generated():
    hs = HypothesisEngine(FIELDS).plan(30)
    assert hs
    assert all("/(abs(" not in h.expression for h in hs)


def test_semantic_aliases_do_not_create_duplicate_trait_pairs():
    hs = HypothesisEngine(FIELDS).plan(30)
    trait_pairs = {tuple(h.traits) for h in hs}
    assert ("sentiment", "text_nlp") not in trait_pairs
