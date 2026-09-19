from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from ..brain.client import BrainClient
from ..brain.discovery import discover
from ..brain.errors import (
    BrainError, BudgetUnknownError, PersonaRequiredError, PermissionErrorBrain,
    RetryableBrainError, RateLimitError,
)
from ..models import Candidate, CandidateState, Lane, Metrics, ResearchProfile
from ..research.bandit import StrategyBandit
from ..research.fingerprints import fingerprint
from ..research.generator import CandidateGenerator
from ..research.scoring import reward
from ..research.validator import validate_expression
from ..storage.db import StateDB
from .guardrails import SubmissionGuard, env_bool
from ..research.superalpha import SuperAlphaAdapter
from ..research.llm import OptionalLLM

LOG = logging.getLogger(__name__)


class EvoForge:
    """Durable closed-loop orchestrator.

    The loop is intentionally boring at the infrastructure layer:
    discover -> generate -> static validate -> simulate -> inspect -> correlation gate
    -> submit -> verify -> learn -> persist -> repeat.
    """
    def __init__(self, db: StateDB, client: BrainClient):
        self.db = db
        self.client = client
        self.max_candidates = int(os.getenv("WQ_MAX_CANDIDATES_PER_CYCLE", "24"))
        self.max_poll = int(os.getenv("WQ_MAX_POLL_SECONDS", "900"))
        self.idle = int(os.getenv("WQ_IDLE_SECONDS", "30"))
        self.reg_target = int(os.getenv("WQ_TARGET_REGULAR", "4"))
        self.super_target = int(os.getenv("WQ_TARGET_SUPER", "1"))
        self.guard = SubmissionGuard(
            write_armed=env_bool("WQ_WRITE_ARMED", False),
            allow_unknown_budget=env_bool("WQ_ALLOW_UNKNOWN_SUBMISSION_BUDGET", False),
        )
        self.profile: ResearchProfile | None = None
        self._last_discovery = 0.0
        self._rediscovery_seconds = int(os.getenv("WQ_REDISCOVERY_SECONDS", "1800"))
        self._corr_fallback = float(os.getenv("WQ_SELF_CORR_FALLBACK", "0.7"))
        self.live_fields: list[dict[str, Any]] = []
        self.llm = OptionalLLM()
        self.allowed_ops: list[str] = []
        self.allowed_fields: list[str] = []

    def _day_key(self) -> str:
        tz = ZoneInfo(os.getenv("WQ_DAY_TIMEZONE", "America/New_York"))
        return datetime.now(tz).strftime("%Y-%m-%d")

    def bootstrap(self) -> dict[str, Any]:
        self.client.login()
        snap = discover(self.client)
        self.profile = snap.profile
        self._last_discovery = time.monotonic()
        self.allowed_ops = [str(x.get("name") or x.get("id") or "") for x in snap.operators]
        common_groups = ["industry", "subindustry", "sector", "market"]
        self.live_fields = self._discover_fields(snap.profile)
        self.allowed_fields = [str(x.get("id")) for x in self.live_fields] + common_groups + [
            "open", "high", "low", "close", "volume", "vwap", "cap", "returns"
        ]
        self.db.set_meta("account_snapshot", {
            "user_id": snap.user.get("id"),
            "profile": snap.profile.__dict__,
            "capability": snap.capability,
            "hashes": snap.hashes,
        })
        self.db.add_event("INFO", "bootstrap", {
            "profile": snap.profile.__dict__, "alpha_count": len(snap.alphas),
            "operator_count": len(snap.operators), "capability": snap.capability,
        })
        return {
            "profile": snap.profile.__dict__,
            "alpha_count": len(snap.alphas),
            "operator_count": len(snap.operators),
            "capability": snap.capability,
        }

    def _discover_fields(self, profile: ResearchProfile) -> list[dict[str, Any]]:
        try:
            return self.client.data_fields_all(
                region=profile.region, universe=profile.universe,
                delay=profile.delay, instrument_type=profile.instrument_type,
            )
        except Exception as exc:
            self.db.add_event("WARNING", "field_discovery_failed", {"error": str(exc)})
            return []

    def _maybe_refresh_discovery(self) -> None:
        if self.profile is None or time.monotonic() - self._last_discovery >= self._rediscovery_seconds:
            self.bootstrap()

    def target_status(self) -> dict[str, Any]:
        day = self._day_key()
        return self.db.ensure_run_target(day, self.reg_target, self.super_target)

    def run_once(self) -> dict[str, Any]:
        if self.profile is None:
            self.bootstrap()
        else:
            self._maybe_refresh_discovery()
        targets = self.target_status()
        if targets["regular_done"] >= targets["regular_target"] and targets["super_done"] >= targets["super_target"]:
            return {"state": "HOLD_COMPLETE", "targets": targets}

        self._resume_pending()
        self._generate_candidates()
        self._simulate_candidates()
        self._evaluate_and_submit_regular()
        self._try_superalpha()
        self._learn_from_recent_results()

        return {"state": "CYCLE_COMPLETE", "targets": self.target_status()}

    def _generate_candidates(self) -> None:
        rows = self.live_fields
        generator = CandidateGenerator([], rows)
        seeds = generator.initial(min(8, self.max_candidates))
        bandit = StrategyBandit(self.db.policy_rows())
        selected_arm = bandit.select()
        existing = self.db.candidates(limit=self.max_candidates)
        live_alphas = self.client.list_alphas()
        live_expr = set()
        for a in live_alphas:
            reg = a.get("regular")
            if isinstance(reg, dict) and reg.get("code"):
                live_expr.add(str(reg.get("code")).replace(" ", ""))
            elif isinstance(reg, str):
                live_expr.add(reg.replace(" ", ""))
        existing_expr = [x.expression for x in existing if x.expression]
        rows = [r for r in seeds if r[0].replace(" ", "") not in live_expr and r[0] not in existing_expr]
        if self.llm.enabled and len(rows) < self.max_candidates:
            try:
                suggestions = self.llm.generate(
                    fields=self.allowed_fields, operators=self.allowed_ops,
                    existing_families=[x.family for x in existing[:30]], n=4
                )
                for item in suggestions:
                    expr = str(item.get("expression", "")).strip()
                    if expr and expr.replace(" ", "") not in live_expr and expr not in existing_expr:
                        rows.append((expr, str(item.get("family", "llm")), str(item.get("hypothesis", "LLM hypothesis")), "llm_generation"))
            except Exception as exc:
                self.db.add_event("WARNING", "llm_generation_failed", {"error": type(exc).__name__, "message": str(exc)[:300]})
        parent_tuples = [(x.expression or "", x.id) for x in existing[:4] if x.expression]
        if parent_tuples:
            muts = generator.mutations(parent_tuples)
            preferred = [m for m in muts if m.strategy == selected_arm]
            if not preferred:
                preferred = muts[:2]
            rows.extend((m.expression, "mutation", m.hypothesis, m.strategy) for m in preferred)
        for expr, family, hypothesis, strategy in rows[:self.max_candidates]:
            lane = Lane.REGULAR
            settings = self._regular_settings()
            cid = str(uuid.uuid4())
            c = Candidate(
                id=cid, lane=lane, expression=expr, settings=settings,
                fingerprint=fingerprint(expr, settings, lane.value), parent_ids=[],
                hypothesis=hypothesis, family=family, strategy_arm=strategy or bandit.select()
            )
            if self.db.insert_candidate(c):
                self.db.add_event("INFO", "candidate_created", {"id": cid, "expression": expr, "strategy": c.strategy_arm})

    def _regular_settings(self) -> dict[str, Any]:
        p = self.profile
        return {
            "instrumentType": p.instrument_type,
            "region": p.region,
            "universe": p.universe,
            "delay": p.delay,
            "decay": p.decay,
            "neutralization": p.neutralization,
            "truncation": p.truncation,
            "pasteurization": p.pasteurization,
            "unitHandling": p.unit_handling,
            "nanHandling": p.nan_handling,
            "language": p.language,
            "visualization": p.visualization,
        }

    def _simulate_candidates(self) -> None:
        candidates = self.db.candidates(states=(CandidateState.CREATED, CandidateState.STATIC_VALID), limit=self.max_candidates)
        for c in candidates:
            if c.lane != Lane.REGULAR or not c.expression:
                continue
            if c.state == CandidateState.CREATED:
                vr = validate_expression(c.expression, allowed_operators=self.allowed_ops, allowed_fields=self.allowed_fields)
                if not vr.ok:
                    c.state = CandidateState.STATIC_REJECTED
                    c.reason = "; ".join(vr.errors)
                    self.db.update_candidate(c)
                    self.db.add_event("INFO", "static_reject", {"id": c.id, "errors": vr.errors})
                    continue
                c.state = CandidateState.STATIC_VALID
                self.db.update_candidate(c)
            c.state = CandidateState.SIM_RUNNING
            self.db.update_candidate(c)
            payload = {"type": "REGULAR", "settings": c.settings, "regular": c.expression}
            try:
                sim_id = self.client.create_simulation(payload)
                c.simulation_id = sim_id
                self.db.update_candidate(c)
                result = self.client.wait_simulation(sim_id, timeout_seconds=self.max_poll)
                alpha_id = result.get("alpha")
                if alpha_id and isinstance(alpha_id, str):
                    c.alpha_id = alpha_id.rstrip("/").split("/")[-1]
                    alpha = self.client.get_alpha(c.alpha_id)
                    c.metrics = Metrics.from_alpha(alpha)
                    c.state = CandidateState.SIM_DONE
                    self.db.update_candidate(c)
                else:
                    c.state = CandidateState.RETRYABLE
                    c.reason = f"simulation had no alpha: {result}"
                    self.db.update_candidate(c)
            except (RateLimitError, RetryableBrainError) as exc:
                c.state = CandidateState.RETRYABLE
                c.reason = str(exc)
                self.db.update_candidate(c)
                self.db.add_event("WARNING", "simulation_retryable", {"id": c.id, "error": str(exc)})
            except BrainError as exc:
                c.state = CandidateState.UNKNOWN
                c.reason = str(exc)
                self.db.update_candidate(c)
                self.db.add_event("ERROR", "simulation_error", {"id": c.id, "error": str(exc)})

    def _platform_quality_gate(self, alpha: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], list[str]]:
        metrics = Metrics.from_alpha(alpha)
        checks = metrics.checks
        fails = [str(x.get("name")) for x in checks if str(x.get("result", "")).upper() == "FAIL"]
        pending = [str(x.get("name")) for x in checks
                   if str(x.get("result", "")).upper() in {"PENDING", "ERROR"}
                   and str(x.get("name", "")) not in {"SELF_CORRELATION", "PROD_CORRELATION", "SUPER_SUBMISSION", "NON_SELF_SUPER_ALPHA", "SELF_SUPER_ALPHA"}]
        missing = []
        if metrics.sharpe is None: missing.append("sharpe")
        if metrics.fitness is None: missing.append("fitness")
        if metrics.turnover is None: missing.append("turnover")
        # Do not hard-code the actual platform threshold. BRAIN's check object is authoritative.
        gate_ok = not fails and not missing and not pending
        if pending:
            missing.append("pending:" + ",".join(pending))
        return gate_ok, checks, missing

    def _corr_max(self, body: dict[str, Any]) -> float | None:
        x = body.get("max")
        try:
            return float(x) if x is not None else None
        except (TypeError, ValueError):
            return None

    def _evaluate_and_submit_regular(self) -> None:
        targets = self.target_status()
        if targets["regular_done"] >= targets["regular_target"]:
            return
        candidates = self.db.candidates(states=(CandidateState.SIM_DONE,), limit=30)
        for c in candidates:
            if targets["regular_done"] >= targets["regular_target"]:
                break
            if not c.alpha_id:
                continue
            try:
                alpha = self.client.get_alpha(c.alpha_id)
                check_body = self.client.check_alpha(c.alpha_id, timeout_seconds=self.max_poll)
                check_block = check_body.get("is", {}) if isinstance(check_body, dict) else {}
                checks = check_block.get("checks") or (alpha.get("is") or {}).get("checks") or []
                quality_ok, checks2, missing = self._platform_quality_gate({**alpha, "is": {**(alpha.get("is") or {}), "checks": checks}})
                checks = checks2
                c.metrics = Metrics.from_alpha({**alpha, "is": {**(alpha.get("is") or {}), "checks": checks}})
                if not quality_ok:
                    c.state = CandidateState.QUALITY_REJECTED
                    c.reason = f"platform quality gate: fails={checks}; missing={missing}"
                    self.db.update_candidate(c)
                    continue
                corr_body = self.client.self_correlation(c.alpha_id, timeout_seconds=self.max_poll)
                c.corr_max = self._corr_max(corr_body)
                corr_limit = self._corr_fallback
                for cc in checks:
                    if cc.get("name") == "SELF_CORRELATION" and cc.get("limit") is not None:
                        try: corr_limit = float(cc.get("limit"))
                        except (TypeError, ValueError): pass
                if c.corr_max is None or abs(c.corr_max) >= corr_limit:
                    c.state = CandidateState.CORR_REJECTED
                    c.reason = f"self-correlation max={c.corr_max}, limit={corr_limit}"
                    self.db.update_candidate(c)
                    continue

                # Discover actual daily submission activity, but do not infer a quota when the
                # endpoint doesn't expose a machine-readable remaining count.
                budget_known, budget_remaining = self._submission_budget()
                decision = self.guard.prewrite(
                    budget_known=budget_known,
                    budget_remaining=budget_remaining,
                    target_remaining=targets["regular_target"] - targets["regular_done"],
                    check_results=checks,
                    corr_max=c.corr_max,
                    metrics=c.metrics,
                    corr_limit=corr_limit,
                )
                if not decision.allowed:
                    c.state = CandidateState.SUBMIT_QUEUED if self.guard.write_armed else CandidateState.QUALITY_REJECTED
                    c.reason = "; ".join(decision.reasons)
                    self.db.update_candidate(c)
                    self.db.add_event("INFO", "submission_blocked", {"id": c.id, "reasons": decision.reasons})
                    continue
                c.state = CandidateState.SUBMIT_PENDING
                self.db.update_candidate(c)
                verdict = self.client.submit_alpha(c.alpha_id, timeout_seconds=self.max_poll)
                if verdict.get("accepted") and verdict.get("status") == "ACTIVE":
                    c.state = CandidateState.ACTIVE
                    self.db.update_candidate(c)
                    self.db.increment_done(self._day_key(), Lane.REGULAR)
                    targets = self.target_status()
                    self.db.add_event("INFO", "regular_active", {"id": c.id, "alpha_id": c.alpha_id})
                elif verdict.get("terminal"):
                    c.state = CandidateState.SUBMIT_REJECTED
                    c.reason = str(verdict.get("reason") or verdict.get("status") or "submit rejected")
                    self.db.update_candidate(c)
                else:
                    c.state = CandidateState.UNKNOWN
                    c.reason = "submission verdict did not become terminal"
                    self.db.update_candidate(c)
            except PersonaRequiredError as exc:
                c.state = CandidateState.UNKNOWN
                c.reason = "Persona verification required; manual completion required"
                self.db.update_candidate(c)
                self.db.add_event("ERROR", "persona_required", {"error": str(exc)})
                break
            except PermissionErrorBrain as exc:
                c.state = CandidateState.UNKNOWN
                c.reason = f"permission boundary: {exc}"
                self.db.update_candidate(c)
                break
            except BrainError as exc:
                c.state = CandidateState.RETRYABLE
                c.reason = str(exc)
                self.db.update_candidate(c)

    def _submission_budget(self) -> tuple[bool, int | None]:
        try:
            body = self.client.activities("submissions")
        except Exception:
            return False, None
        # We only trust explicit fields containing both a value and a remaining/limit semantic.
        candidates: list[int] = []
        def walk(x: Any) -> None:
            if isinstance(x, dict):
                keys = {str(k).lower(): v for k, v in x.items()}
                for k, v in keys.items():
                    if k in {"remaining", "remainingtoday", "remaining_today"}:
                        try: candidates.append(int(v))
                        except Exception: pass
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(body)
        if candidates:
            return True, min(candidates)
        return False, None

    def _try_superalpha(self) -> None:
        targets = self.target_status()
        if targets["super_done"] >= targets["super_target"]:
            return
        alphas = self.client.list_alphas()
        adapter = SuperAlphaAdapter(self.client, self.profile)
        options = self.client.simulation_options()
        info = adapter.discover(alphas, options)
        self.db.add_event("INFO", "superalpha_discovery", {
            "type_supported": info["type_supported"],
            "active_regular_count": info["active_regular_count"],
            "existing_super_shape": info["existing_super_shape"],
        })
        # The exact SUPER write schema is never guessed.
        if not info["type_supported"]:
            return
        if info["active_regular_count"] < 10:
            return
        # Use a simple portfolio-diversifying selection idea, but only as a candidate draft.
        selection = "self_correlation < 0.5"
        combo = "1"
        try:
            payload = adapter.build_payload(selection_expression=selection, combo_expression=combo)
        except BrainError as exc:
            self.db.add_event("WARNING", "superalpha_template_error", {"error": str(exc)})
            return
        if not payload:
            self.db.add_event("INFO", "superalpha_manual_template_required", {
                "message": "SUPER type is discoverable, but no live payload template is configured; no guessed write payload was sent."
            })
            return
        if not self.guard.write_armed:
            return
        # SUPER simulation execution is deliberately separate from regular lane because its
        # platform checks differ. We accept only a verified ACTIVE result.
        try:
            sim_id = self.client.create_simulation(payload)
            result = self.client.wait_simulation(sim_id, timeout_seconds=self.max_poll)
            alpha_id = result.get("alpha")
            if not alpha_id:
                return
            alpha = self.client.get_alpha(str(alpha_id).rstrip("/").split("/")[-1])
            aid = str(alpha.get("id") or str(alpha_id).rstrip("/").split("/")[-1])
            corr = self._corr_max(self.client.self_correlation(aid, timeout_seconds=self.max_poll))
            metrics = Metrics.from_alpha(alpha)
            checks = metrics.checks
            decision = self.guard.prewrite(
                budget_known=False, budget_remaining=None, target_remaining=targets["super_target"] - targets["super_done"],
                check_results=checks, corr_max=corr, metrics=metrics,
                corr_limit=next((float(x.get("limit")) for x in checks if x.get("name") == "SELF_CORRELATION" and x.get("limit") is not None), self._corr_fallback),
            )
            if not decision.allowed:
                return
            verdict = self.client.submit_alpha(aid, timeout_seconds=self.max_poll)
            if verdict.get("accepted") and verdict.get("status") == "ACTIVE":
                self.db.increment_done(self._day_key(), Lane.SUPER)
                self.db.add_event("INFO", "super_active", {"alpha_id": aid})
        except BrainError as exc:
            self.db.add_event("ERROR", "superalpha_error", {"error": str(exc)})

    def _resume_pending(self) -> None:
        # On restart, never blindly resubmit. Re-read platform status for known alpha IDs.
        pending = self.db.candidates(states=(CandidateState.SUBMIT_PENDING, CandidateState.UNKNOWN, CandidateState.SIM_RUNNING), limit=100)
        for c in pending:
            try:
                if c.alpha_id:
                    a = self.client.get_alpha(c.alpha_id)
                    status = str(a.get("status", "")).upper()
                    if status == "ACTIVE":
                        if c.state != CandidateState.ACTIVE:
                            c.state = CandidateState.ACTIVE
                            c.metrics = Metrics.from_alpha(a)
                            self.db.update_candidate(c)
                            self.db.increment_done(self._day_key(), c.lane)
                    elif status == "UNSUBMITTED":
                        # Leave for normal gate evaluation; do NOT auto-submit at resume time.
                        c.state = CandidateState.SIM_DONE if c.alpha_id else CandidateState.UNKNOWN
                        self.db.update_candidate(c)
            except Exception as exc:
                self.db.add_event("WARNING", "resume_probe_failed", {"id": c.id, "error": str(exc)})

    def _learn_from_recent_results(self) -> None:
        rows = self.db.candidates(limit=100)
        for c in rows:
            if not c.strategy_arm:
                continue
            if c.state not in {CandidateState.ACTIVE, CandidateState.QUALITY_REJECTED, CandidateState.CORR_REJECTED, CandidateState.SUBMIT_REJECTED}:
                continue
            accepted = c.state == CandidateState.ACTIVE
            r = reward(c.metrics, c.corr_max, accepted)
            # Prevent duplicate learning from every cycle using metadata marker.
            key = f"learned:{c.id}"
            if not self.db.get_meta(key):
                self.db.update_policy(c.strategy_arm, r)
                self.db.set_meta(key, True)

    def status(self) -> dict[str, Any]:
        target = self.target_status()
        states = self.db.candidates(limit=1000)
        counts: dict[str, int] = defaultdict(int)
        for c in states:
            counts[c.state.value] += 1
        return {"target": target, "candidate_states": dict(counts), "write_armed": self.guard.write_armed,
                "profile": self.profile.__dict__ if self.profile else None, "llm_enabled": self.llm.enabled}

    def run_forever(self) -> None:
        while True:
            try:
                result = self.run_once()
                LOG.info("cycle: %s", json.dumps(result, default=str))
                if result.get("state") == "HOLD_COMPLETE":
                    # Continue monitoring, but do not generate/submission churn.
                    time.sleep(max(self.idle, 60))
                else:
                    time.sleep(self.idle)
            except PersonaRequiredError:
                LOG.error("Persona verification is required. Automation is paused until manual verification completes.")
                time.sleep(300)
            except PermissionErrorBrain as exc:
                LOG.error("Permission boundary: %s", exc)
                time.sleep(300)
            except (RateLimitError, RetryableBrainError) as exc:
                LOG.warning("Transient platform condition: %s", exc)
                time.sleep(max(self.idle, 60))
            except Exception as exc:
                self.db.add_event("ERROR", "orchestrator_crash_recovery", {"error": repr(exc)})
                LOG.exception("orchestrator cycle failure")
                # Process stays alive; state is persisted and next cycle resumes.
                time.sleep(max(self.idle, 60))
