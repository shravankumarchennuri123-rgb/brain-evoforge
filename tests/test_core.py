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


def test_profile_prefers_most_recent_active_regular(monkeypatch):
    from wq_evo.brain.discovery import discover_profile

    monkeypatch.delenv("WQ_REGION", raising=False)
    monkeypatch.delenv("WQ_UNIVERSE", raising=False)
    monkeypatch.delenv("WQ_DELAY", raising=False)

    rows = [
        {
            "id": "old",
            "status": "ACTIVE",
            "type": "REGULAR",
            "dateModified": "2026-01-01T00:00:00Z",
            "settings": {"region": "USA", "universe": "TOP3000", "delay": 1, "instrumentType": "EQUITY"},
        },
        {
            "id": "new",
            "status": "ACTIVE",
            "type": "REGULAR",
            "dateModified": "2026-09-18T00:00:00Z",
            "settings": {"region": "DEU", "universe": "TOP500", "delay": 1, "instrumentType": "EQUITY"},
        },
        {
            "id": "recent-sim",
            "status": "UNSUBMITTED",
            "type": "REGULAR",
            "dateModified": "2026-09-19T00:00:00Z",
            "settings": {"region": "GBR", "universe": "TOP700", "delay": 1, "instrumentType": "EQUITY"},
        },
    ]

    p = discover_profile(rows)
    assert (p.region, p.universe, p.delay) == ("DEU", "TOP500", 1)
