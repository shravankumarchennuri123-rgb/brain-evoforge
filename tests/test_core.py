from wq_evo.models import CandidateState
from wq_evo.research.fingerprints import fingerprint, structural_signature
from wq_evo.research.validator import nesting_depth, validate_expression


def test_fingerprint_changes_with_settings():
    a = fingerprint("rank(close)", {"region":"USA"}, "REGULAR")
    b = fingerprint("rank(close)", {"region":"CHN"}, "REGULAR")
    assert a != b


def test_structural_signature_removes_numeric_literals():
    assert structural_signature("rank(ts_mean(close, 20))") == structural_signature("rank(ts_mean(close, 126))")


def test_nesting_depth():
    assert nesting_depth("rank(ts_mean(close,20))") == 2


def test_validator_rejects_bad_expression():
    r = validate_expression("rank(close", allowed_operators=["rank"], allowed_fields=["close"])
    assert not r.ok


def test_state_enum():
    assert CandidateState.ACTIVE.value == "ACTIVE"
