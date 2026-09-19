from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests
from requests.auth import HTTPBasicAuth

from .errors import (
    BrainError,
    PersonaRequiredError,
    PermissionErrorBrain,
    RateLimitError,
    RetryableBrainError,
)

LOG = logging.getLogger(__name__)
API_BASE = "https://api.worldquantbrain.com"


@dataclass
class ResponseEnvelope:
    status: int
    headers: dict[str, str]
    body: Any
    text: str


class BrainClient:
    """Conservative REST client.

    Design goals:
    - dynamic discovery instead of fixed platform assumptions
    - fail closed on ambiguous writes
    - one transparent re-login on 401
    - Retry-After aware 429/503 handling
    - no CAPTCHA, stealth, fingerprint spoofing, or browser-bypass logic
    """

    def __init__(self, email: str, password: str, *, max_retries: int = 4, base_url: str = API_BASE):
        self.email = email
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, application/json;version=2.0",
            "Content-Type": "application/json",
            "User-Agent": "brain-evoforge/0.1",
        })
        self._did_relogin = False
        self._session_adopted = False

    def adopt_authenticated_session(self, session: requests.Session) -> None:
        """Adopt an already Persona-verified BRAIN session for this process.

        Intended for local/Colab execution after the user completes the normal
        BRAIN Persona flow. The session remains in memory and is never persisted
        by EvoForge.
        """
        if not isinstance(session, requests.Session):
            raise TypeError("session must be a requests.Session")
        self.session = session
        self._session_adopted = True
        self._did_relogin = False

    def _retry_after(self, headers: dict[str, str], default: float) -> float:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return default
        try:
            return max(0.5, min(float(raw), 180.0))
        except ValueError:
            return default

    def _decode(self, response: requests.Response) -> ResponseEnvelope:
        text = response.text or ""
        try:
            body = response.json() if text else {}
        except ValueError:
            body = None
        return ResponseEnvelope(response.status_code, dict(response.headers), body, text)

    def request(self, method: str, path: str, *, json_body: Any = None, params: dict[str, Any] | None = None,
                timeout: tuple[float, float] = (15, 90), allow_401_relogin: bool = True) -> ResponseEnvelope:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        for attempt in range(self.max_retries + 1):
            try:
                r = self.session.request(
                    method, url, json=json_body, params=params, timeout=timeout,
                    auth=HTTPBasicAuth(self.email, self.password),
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= self.max_retries:
                    raise RetryableBrainError(f"network failure: {exc}") from exc
                time.sleep(min(60, 2 ** attempt + random.random()))
                continue

            # BRAIN can return HTTP 401 with an "inquiry" payload when Persona/identity
            # verification is required. Detect that before the generic 401 re-login path.
            env = self._decode(r)
            if r.status_code == 401 and isinstance(env.body, dict) and env.body.get("inquiry"):
                raise PersonaRequiredError(str(env.body["inquiry"]))

            if r.status_code == 401 and allow_401_relogin and not self._did_relogin:
                self._did_relogin = True
                self.login(force=True)
                continue

            if r.status_code in (429, 503):
                delay = self._retry_after(dict(r.headers), 2 ** attempt)
                if attempt >= self.max_retries:
                    raise RateLimitError(f"HTTP {r.status_code}", delay)
                time.sleep(delay)
                continue

            if r.status_code == 403:
                body_txt = r.text[:500]
                if "inquiry" in body_txt.lower() or "persona" in body_txt.lower():
                    raise PersonaRequiredError(body_txt)
                if isinstance(env.body, dict) and "detail" in env.body:
                    raise PermissionErrorBrain(str(env.body["detail"]))

            if r.status_code >= 500:
                if attempt >= self.max_retries:
                    raise RetryableBrainError(f"HTTP {r.status_code}: {r.text[:500]}")
                time.sleep(min(60, 2 ** attempt + random.random()))
                continue
            if r.status_code >= 400:
                return env
            self._did_relogin = False
            return env

        raise RetryableBrainError(f"request failed after retries: {method} {url}")

    def login(self, *, force: bool = False) -> dict[str, Any]:
        if self._session_adopted and not force:
            return {"reused_authenticated_session": True}
        env = self.request("POST", "/authentication", allow_401_relogin=not force)
        if env.status not in (200, 201):
            raise PermissionErrorBrain(f"authentication failed: HTTP {env.status} {env.text[:500]}")
        if isinstance(env.body, dict) and env.body.get("inquiry"):
            raise PersonaRequiredError(str(env.body["inquiry"]))
        self._session_adopted = False
        return env.body if isinstance(env.body, dict) else {}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        env = self.request("GET", path, params=params)
        if env.body is None:
            raise BrainError(f"invalid JSON from {path}: {env.text[:500]}")
        return env.body

    def post_json(self, path: str, payload: Any) -> ResponseEnvelope:
        return self.request("POST", path, json_body=payload)

    def get_user(self) -> dict[str, Any]:
        body = self.get_json("/users/self")
        return body if isinstance(body, dict) else {}

    def list_alphas(self, *, status: str | None = None, page_limit: int = 100) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            params: dict[str, Any] = {"limit": page_limit, "offset": offset}
            if status:
                params["status"] = status
            body = self.get_json("/users/self/alphas", params=params)
            rows = body.get("results", []) if isinstance(body, dict) else []
            all_rows.extend(x for x in rows if isinstance(x, dict))
            if len(rows) < page_limit:
                break
            offset += page_limit
        return all_rows

    def activities(self, kind: str) -> dict[str, Any] | list[Any]:
        return self.get_json(f"/users/self/activities/{kind}")

    def simulation_options(self) -> dict[str, Any]:
        env = self.request("OPTIONS", "/simulations")
        if env.status >= 400:
            return {}
        return env.body if isinstance(env.body, dict) else {}

    def operators(self) -> list[dict[str, Any]]:
        body = self.get_json("/operators")
        return body if isinstance(body, list) else body.get("results", []) if isinstance(body, dict) else []

    def data_fields(self, *, region: str, universe: str, delay: int, instrument_type: str = "EQUITY",
                    limit: int = 200, offset: int = 0) -> dict[str, Any]:
        params = {
            "region": region, "universe": universe, "delay": delay,
            "instrumentType": instrument_type, "limit": limit, "offset": offset,
        }
        body = self.get_json("/data-fields", params=params)
        return body if isinstance(body, dict) else {"results": []}

    def data_fields_all(self, *, region: str, universe: str, delay: int, instrument_type: str = "EQUITY", max_rows: int = 5000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            body = self.data_fields(region=region, universe=universe, delay=delay, instrument_type=instrument_type,
                                    offset=offset)
            batch = body.get("results", [])
            rows.extend(x for x in batch if isinstance(x, dict))
            if len(rows) >= max_rows or len(batch) < 200:
                break
            offset += 200
        return rows

    def create_simulation(self, payload: dict[str, Any]) -> str:
        env = self.post_json("/simulations", payload)
        if env.status not in (200, 201, 202):
            raise BrainError(f"simulation rejected: HTTP {env.status}: {env.text[:800]}")
        location = env.headers.get("Location") or env.headers.get("location")
        if not location:
            raise BrainError("simulation accepted without Location header")
        return location.rstrip("/").split("/")[-1]

    def wait_simulation(self, sim_id: str, *, timeout_seconds: int = 900) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            env = self.request("GET", f"/simulations/{sim_id}")
            body = env.body if isinstance(env.body, dict) else {}
            # Alpha presence is the strong completion signal; WARNING may still have a valid alpha.
            if body.get("alpha") or body.get("children") or str(body.get("status", "")).upper() in {
                "COMPLETE", "WARNING", "CANCELLED", "TIMEOUT", "ERROR", "FAIL"
            }:
                return body
            time.sleep(max(1.0, min(self._retry_after(env.headers, 5.0), 30.0)))
        raise RetryableBrainError(f"simulation {sim_id} timed out")

    def get_alpha(self, alpha_id: str) -> dict[str, Any]:
        body = self.get_json(f"/alphas/{alpha_id}")
        return body if isinstance(body, dict) else {}

    def check_alpha(self, alpha_id: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            env = self.request("GET", f"/alphas/{alpha_id}/check")
            if env.body:
                return env.body if isinstance(env.body, dict) else {}
            time.sleep(max(1.0, min(self._retry_after(env.headers, 5), 30.0)))
        raise RetryableBrainError(f"check {alpha_id} timed out")

    def self_correlation(self, alpha_id: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            env = self.request("GET", f"/alphas/{alpha_id}/correlations/self")
            if env.body:
                return env.body if isinstance(env.body, dict) else {}
            time.sleep(max(1.0, min(self._retry_after(env.headers, 5), 30.0)))
        raise RetryableBrainError(f"self-correlation {alpha_id} timed out")

    def prod_correlation(self, alpha_id: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            env = self.request("GET", f"/alphas/{alpha_id}/correlations/prod")
            if env.body:
                return env.body if isinstance(env.body, dict) else {}
            time.sleep(max(1.0, min(self._retry_after(env.headers, 5), 30.0)))
        raise RetryableBrainError(f"prod-correlation {alpha_id} timed out")

    def alpha_pnl(self, alpha_id: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            env = self.request("GET", f"/alphas/{alpha_id}/recordsets/pnl")
            if env.body:
                return env.body if isinstance(env.body, dict) else {}
            time.sleep(max(1.0, min(self._retry_after(env.headers, 5), 30.0)))
        raise RetryableBrainError(f"PnL {alpha_id} timed out")

    def submit_alpha(self, alpha_id: str, *, timeout_seconds: int = 900) -> dict[str, Any]:
        env = self.request("POST", f"/alphas/{alpha_id}/submit")
        if env.status >= 400 and env.status not in (429, 503):
            return {"terminal": True, "status": env.status, "body": env.body, "text": env.text}
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            env = self.request("GET", f"/alphas/{alpha_id}/submit")
            last = env.body if isinstance(env.body, dict) else {}
            is_block = last.get("is") or {}
            checks = is_block.get("checks") or []
            corr = next((c for c in checks if c.get("name") == "SELF_CORRELATION"), None)
            status = str(last.get("status", "")).upper()
            if status == "ACTIVE":
                return {"terminal": True, "accepted": True, "status": status, "body": last}
            if corr and corr.get("result") == "FAIL":
                return {"terminal": True, "accepted": False, "status": status, "reason": "SELF_CORRELATION", "body": last}
            if any(c.get("result") == "FAIL" for c in checks):
                return {"terminal": True, "accepted": False, "status": status, "reason": "CHECK_FAIL", "body": last}
            time.sleep(max(1.0, min(self._retry_after(env.headers, 8), 60.0)))
        return {"terminal": False, "accepted": False, "status": str(last.get("status", "UNKNOWN")), "body": last}
