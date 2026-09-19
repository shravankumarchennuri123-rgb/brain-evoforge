from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .client import BrainClient
from .errors import PersonaRequiredError, PermissionErrorBrain
from ..models import ResearchProfile

LOG = logging.getLogger(__name__)


@dataclass
class AccountSnapshot:
    user: dict[str, Any]
    alphas: list[dict[str, Any]]
    operators: list[dict[str, Any]]
    simulation_options: dict[str, Any]
    competitions: list[dict[str, Any]]
    activities: dict[str, Any]
    profile: ResearchProfile
    capability: dict[str, bool]
    hashes: dict[str, str]


def _hash_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def discover_profile(alphas: list[dict[str, Any]]) -> ResearchProfile:
    env_region = os.getenv("WQ_REGION") or None
    env_universe = os.getenv("WQ_UNIVERSE") or None
    env_delay = os.getenv("WQ_DELAY")
    env_inst = os.getenv("WQ_INSTRUMENT_TYPE") or "EQUITY"
    env_decay = int(os.getenv("WQ_DECAY", "0"))
    env_neut = os.getenv("WQ_NEUTRALIZATION", "SUBINDUSTRY")
    env_trunc = float(os.getenv("WQ_TRUNCATION", "0.08"))

    tuples: list[tuple[str, str, int, str]] = []
    for a in alphas:
        s = a.get("settings") or {}
        if isinstance(s, dict) and s.get("region") and s.get("universe") and s.get("delay") is not None:
            tuples.append((str(s["region"]), str(s["universe"]), int(s["delay"]), str(s.get("instrumentType", env_inst))))
    if not tuples and (not env_region or not env_universe or env_delay is None):
        raise RuntimeError("No account profile can be inferred. Set WQ_REGION, WQ_UNIVERSE and WQ_DELAY after discovery.")

    if env_region and env_universe and env_delay is not None:
        region, universe, delay, inst = env_region, env_universe, int(env_delay), env_inst
    else:
        region, universe, delay, inst = Counter(tuples).most_common(1)[0][0]
    return ResearchProfile(inst, region, universe, delay, env_decay, env_neut, env_trunc)


def discover(client: BrainClient) -> AccountSnapshot:
    user = client.get_user()
    alphas = client.list_alphas()
    ops = client.operators()
    options = client.simulation_options()
    competitions: list[dict[str, Any]] = []
    try:
        raw = client.get_json("/users/self/competitions")
        competitions = raw.get("results", []) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    except Exception as exc:
        LOG.warning("competition discovery unavailable: %s", exc)
    activities: dict[str, Any] = {}
    for kind in ("submissions", "simulations"):
        try:
            activities[kind] = client.activities(kind)
        except Exception as exc:
            activities[kind] = {"error": type(exc).__name__}
    profile = discover_profile(alphas)

    return AccountSnapshot(
        user=user,
        alphas=alphas,
        operators=ops,
        simulation_options=options,
        competitions=competitions,
        activities=activities,
        profile=profile,
        capability={
            "can_simulate": bool(options),
            "has_regular_alphas": any(str(a.get("type", "")).upper() == "REGULAR" for a in alphas),
            "has_superalpha": any(str(a.get("type", "")).upper() == "SUPER" for a in alphas),
        },
        hashes={
            "operators": _hash_json(ops),
            "simulation_options": _hash_json(options),
            "alphas": _hash_json([(a.get("id"), a.get("status"), a.get("dateModified")) for a in alphas]),
        },
    )
