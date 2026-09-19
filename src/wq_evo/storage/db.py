from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..models import Candidate, CandidateState, Lane, Metrics, utcnow


class StateDB:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candidates(
              id TEXT PRIMARY KEY,
              lane TEXT NOT NULL,
              expression TEXT,
              settings_json TEXT NOT NULL,
              state TEXT NOT NULL,
              fingerprint TEXT NOT NULL UNIQUE,
              parent_ids_json TEXT NOT NULL,
              hypothesis TEXT,
              family TEXT,
              strategy_arm TEXT,
              alpha_id TEXT,
              simulation_id TEXT,
              metrics_json TEXT NOT NULL,
              corr_max REAL,
              reason TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_state ON candidates(state);
            CREATE INDEX IF NOT EXISTS idx_candidates_alpha ON candidates(alpha_id);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              level TEXT NOT NULL,
              kind TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy(
              arm TEXT PRIMARY KEY,
              pulls INTEGER NOT NULL DEFAULT 0,
              reward_sum REAL NOT NULL DEFAULT 0,
              reward_sq_sum REAL NOT NULL DEFAULT 0,
              last_reward REAL,
              last_updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_targets(
              day_key TEXT PRIMARY KEY,
              regular_target INTEGER NOT NULL,
              super_target INTEGER NOT NULL,
              regular_done INTEGER NOT NULL DEFAULT 0,
              super_done INTEGER NOT NULL DEFAULT 0
            );
            """)

    def set_meta(self, key: str, value: Any) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                              (key, json.dumps(value, default=str)))

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def insert_candidate(self, c: Candidate) -> bool:
        with self.lock, self.conn:
            try:
                self.conn.execute("""
                  INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    c.id, c.lane.value, c.expression, json.dumps(c.settings, default=str), c.state.value,
                    c.fingerprint, json.dumps(c.parent_ids), c.hypothesis, c.family, c.strategy_arm,
                    c.alpha_id, c.simulation_id, json.dumps(c.metrics.__dict__, default=str), c.corr_max,
                    c.reason, c.created_at.isoformat(), c.updated_at.isoformat()
                ))
                return True
            except sqlite3.IntegrityError:
                return False

    def update_candidate(self, c: Candidate) -> None:
        c.updated_at = utcnow()
        with self.lock, self.conn:
            self.conn.execute("""
              UPDATE candidates SET lane=?, expression=?, settings_json=?, state=?, fingerprint=?, parent_ids_json=?,
                hypothesis=?, family=?, strategy_arm=?, alpha_id=?, simulation_id=?, metrics_json=?, corr_max=?, reason=?, updated_at=?
              WHERE id=?
            """, (
                c.lane.value, c.expression, json.dumps(c.settings, default=str), c.state.value, c.fingerprint,
                json.dumps(c.parent_ids), c.hypothesis, c.family, c.strategy_arm, c.alpha_id, c.simulation_id,
                json.dumps(c.metrics.__dict__, default=str), c.corr_max, c.reason, c.updated_at.isoformat(), c.id
            ))

    def get_candidate(self, cid: str) -> Candidate | None:
        row = self.conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        return self._row(row) if row else None

    def find_by_fingerprint(self, fingerprint: str) -> Candidate | None:
        row = self.conn.execute("SELECT * FROM candidates WHERE fingerprint=?", (fingerprint,)).fetchone()
        return self._row(row) if row else None

    def candidates(self, states: tuple[CandidateState, ...] | None = None, limit: int = 100) -> list[Candidate]:
        if states:
            placeholders = ",".join("?" for _ in states)
            rows = self.conn.execute(f"SELECT * FROM candidates WHERE state IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?",
                                     tuple(x.value for x in states) + (limit,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM candidates ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def add_event(self, level: str, kind: str, payload: dict[str, Any]) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO events(ts,level,kind,payload_json) VALUES(?,?,?,?)",
                              (utcnow().isoformat(), level, kind, json.dumps(payload, default=str)))

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def ensure_run_target(self, day_key: str, regular: int, super_target: int) -> dict[str, Any]:
        # Mission target is persistent across restarts and day-rollovers.
        if self.get_meta("mission_initialized") is None:
            self.set_meta("mission_initialized", True)
            self.set_meta("mission_regular_target", regular)
            self.set_meta("mission_super_target", super_target)
            self.set_meta("mission_regular_done", 0)
            self.set_meta("mission_super_done", 0)
        return {
            "regular_target": int(self.get_meta("mission_regular_target", regular)),
            "super_target": int(self.get_meta("mission_super_target", super_target)),
            "regular_done": int(self.get_meta("mission_regular_done", 0)),
            "super_done": int(self.get_meta("mission_super_done", 0)),
            "mission_initialized": True,
        }

    def increment_done(self, day_key: str, lane: Lane) -> None:
        key = "mission_regular_done" if lane == Lane.REGULAR else "mission_super_done"
        current = int(self.get_meta(key, 0))
        self.set_meta(key, current + 1)

    def policy_rows(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM policy ORDER BY arm").fetchall()]

    def update_policy(self, arm: str, reward: float) -> None:
        with self.lock, self.conn:
            self.conn.execute("""
              INSERT INTO policy(arm,pulls,reward_sum,reward_sq_sum,last_reward,last_updated)
              VALUES(?,1,?,?,?,?)
              ON CONFLICT(arm) DO UPDATE SET
                pulls=pulls+1,
                reward_sum=reward_sum+excluded.reward_sum,
                reward_sq_sum=reward_sq_sum+excluded.reward_sq_sum,
                last_reward=excluded.last_reward,
                last_updated=excluded.last_updated
            """, (arm, reward, reward * reward, reward, utcnow().isoformat()))

    @staticmethod
    def _row(row: sqlite3.Row) -> Candidate:
        metrics = json.loads(row["metrics_json"])
        return Candidate(
            id=row["id"], lane=Lane(row["lane"]), expression=row["expression"], settings=json.loads(row["settings_json"]),
            state=CandidateState(row["state"]), fingerprint=row["fingerprint"], parent_ids=json.loads(row["parent_ids_json"]),
            hypothesis=row["hypothesis"] or "", family=row["family"] or "unknown", strategy_arm=row["strategy_arm"] or "baseline",
            alpha_id=row["alpha_id"], simulation_id=row["simulation_id"], metrics=Metrics(**metrics), corr_max=row["corr_max"],
            reason=row["reason"], created_at=__import__("datetime").datetime.fromisoformat(row["created_at"]),
            updated_at=__import__("datetime").datetime.fromisoformat(row["updated_at"])
        )
