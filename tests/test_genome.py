from wq_evo.research.genome import ExpressionSyntaxError, build_genome, parse_expression


CATALOG = [
    {
        "id": "foo_score",
        "category": "Analyst",
        "dataset": "Forecast Dataset",
        "type": "MATRIX",
        "coverage": 0.98,
        "dateCoverage": 0.99,
        "alphaCount": 4,
        "userCount": 3,
        "description": "Analyst EPS estimate revision score",
    },
    {
        "id": "close",
        "category": "Price Volume",
        "dataset": "Daily Prices",
        "type": "MATRIX",
    },
]


def test_nested_expression_genome():
    g = build_genome("rank(ts_delta(foo_score,20))", CATALOG)
    assert g.canonical_expression == "rank(ts_delta(foo_score,20))"
    assert g.operators == ("rank", "ts_delta")
    assert g.windows == (20,)
    assert g.fields[0].field_id == "foo_score"
    assert "analyst_expectations" in g.semantic_traits
    assert g.depth >= 3


def test_arithmetic_and_groups():
    g = build_genome("0.5*group_rank(foo_score,industry)-0.5*rank(close)", CATALOG)
    assert set(g.groups) == {"industry"}
    assert {"foo_score", "close"} == {f.field_id for f in g.fields}
    assert g.binary_operator_count >= 3


def test_rejects_unparsed_text():
    try:
        parse_expression("rank(foo_score) @ 2")
    except ExpressionSyntaxError:
        return
    raise AssertionError("invalid character was accepted")


def test_unary_minus():
    g = build_genome("-ts_delta(close,5)")
    assert g.operators == ("ts_delta",)
    assert g.constants == (5.0,)
