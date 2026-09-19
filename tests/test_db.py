from wq_evo.models import Candidate, CandidateState, Lane
from wq_evo.storage.db import StateDB
from wq_evo.research.fingerprints import fingerprint


def test_db_idempotent_fingerprint(tmp_path):
    db = StateDB(str(tmp_path / "x.sqlite3"))
    settings = {"region": "USA", "universe": "TOP3000", "delay": 1}
    fp = fingerprint("rank(close)", settings, "REGULAR")
    c1 = Candidate("1", Lane.REGULAR, "rank(close)", settings, fingerprint=fp)
    c2 = Candidate("2", Lane.REGULAR, "rank(close)", settings, fingerprint=fp)
    assert db.insert_candidate(c1)
    assert not db.insert_candidate(c2)
    assert db.find_by_fingerprint(fp).id == "1"


def test_mission_target_persists_across_day_keys(tmp_path):
    db = StateDB(str(tmp_path / "x.sqlite3"))
    a = db.ensure_run_target("2026-09-19", 4, 1)
    db.increment_done("2026-09-19", Lane.REGULAR)
    b = db.ensure_run_target("2026-09-20", 4, 1)
    assert a["regular_target"] == 4
    assert b["regular_done"] == 1
