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

    for key in (
        "WQ_REGION", "WQ_UNIVERSE", "WQ_DELAY", "WQ_INSTRUMENT_TYPE",
        "WQ_DECAY", "WQ_NEUTRALIZATION", "WQ_TRUNCATION",
        "WQ_PASTEURIZATION", "WQ_UNIT_HANDLING", "WQ_NAN_HANDLING",
        "WQ_LANGUAGE", "WQ_VISUALIZATION",
    ):
        monkeypatch.delenv(key, raising=False)

    rows = [
        {
            "id": "old",
            "status": "ACTIVE",
            "type": "REGULAR",
            "dateModified": "2026-01-01T00:00:00Z",
            "settings": {
                "region": "USA", "universe": "TOP3000", "delay": 1,
                "decay": 0, "neutralization": "SUBINDUSTRY",
                "truncation": 0.08, "pasteurization": "ON",
                "unitHandling": "VERIFY", "nanHandling": "ON",
                "language": "FASTEXPR", "visualization": False,
            },
        },
        {
            "id": "new",
            "status": "ACTIVE",
            "type": "REGULAR",
            "dateModified": "2026-09-18T00:00:00Z",
            "settings": {
                "region": "DEU", "universe": "TOP500", "delay": 1,
                "decay": 4, "neutralization": "INDUSTRY",
                "truncation": 0.01, "pasteurization": "ON",
                "unitHandling": "VERIFY", "nanHandling": "OFF",
                "language": "FASTEXPR", "visualization": True,
            },
        },
        {
            "id": "recent-sim",
            "status": "UNSUBMITTED",
            "type": "REGULAR",
            "dateModified": "2026-09-19T00:00:00Z",
            "settings": {
                "region": "GBR", "universe": "TOP700", "delay": 1,
                "decay": 10, "neutralization": "SECTOR",
                "truncation": 0.09, "pasteurization": "ON",
                "unitHandling": "VERIFY", "nanHandling": "ON",
                "language": "FASTEXPR", "visualization": False,
            },
        },
    ]

    p = discover_profile(rows)

    assert (p.region, p.universe, p.delay) == ("DEU", "TOP500", 1)
    assert p.decay == 4
    assert p.neutralization == "INDUSTRY"
    assert p.truncation == 0.01
    assert p.pasteurization == "ON"
    assert p.unit_handling == "VERIFY"
    assert p.nan_handling == "OFF"
    assert p.language == "FASTEXPR"
    assert p.visualization is True

