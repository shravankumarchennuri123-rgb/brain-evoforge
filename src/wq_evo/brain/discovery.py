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
    # Explicit environment settings override discovery. Otherwise inherit the
    # complete settings from the most recently modified ACTIVE REGULAR alpha.
    # If there is no ACTIVE REGULAR, fall back to the most recent REGULAR object.
    env_region = os.getenv("WQ_REGION") or None
    env_universe = os.getenv("WQ_UNIVERSE") or None
    env_delay = os.getenv("WQ_DELAY")
    env_inst = os.getenv("WQ_INSTRUMENT_TYPE") or None
    env_decay = os.getenv("WQ_DECAY")
    env_neut = os.getenv("WQ_NEUTRALIZATION")
    env_trunc = os.getenv("WQ_TRUNCATION")
    env_pasteurization = os.getenv("WQ_PASTEURIZATION")
    env_unit_handling = os.getenv("WQ_UNIT_HANDLING")
    env_nan_handling = os.getenv("WQ_NAN_HANDLING")
    env_language = os.getenv("WQ_LANGUAGE")
    env_visualization = os.getenv("WQ_VISUALIZATION")

    def row_time(a: dict[str, Any]) -> str:
        return str(a.get("dateModified") or a.get("dateCreated") or "")

    active = [
        a for a in alphas
        if str(a.get("type", "")).upper() == "REGULAR"
        and str(a.get("status", "")).upper() == "ACTIVE"
        and isinstance(a.get("settings"), dict)
    ]
    regular = [
        a for a in alphas
        if str(a.get("type", "")).upper() == "REGULAR"
        and isinstance(a.get("settings"), dict)
    ]
    source = sorted(active or regular, key=row_time, reverse=True)
    if not source and not (env_region and env_universe and env_delay is not None):
        raise RuntimeError(
            "No REGULAR alpha/simulation profile is available. "
            "Set WQ_REGION, WQ_UNIVERSE and WQ_DELAY explicitly."
        )

    base = (source[0].get("settings") or {}) if source else {}
    region = str(env_region or base.get("region") or "")
    universe = str(env_universe or base.get("universe") or "")
    if env_delay is not None:
        delay = int(env_delay)
    elif base.get("delay") is not None:
        delay = int(base["delay"])
    else:
        raise RuntimeError("No delay is available from the live REGULAR profile.")

    if not region or not universe:
        raise RuntimeError(
            "Live REGULAR profile is incomplete; set WQ_REGION and WQ_UNIVERSE explicitly."
        )

    inst = str(env_inst or base.get("instrumentType") or "EQUITY")
    decay = int(env_decay) if env_decay is not None else int(base.get("decay", 0))
    neutralization = str(env_neut or base.get("neutralization") or "SUBINDUSTRY")
    truncation = float(env_trunc) if env_trunc is not None else float(base.get("truncation", 0.08))
    pasteurization = str(env_pasteurization or base.get("pasteurization") or "ON")
    unit_handling = str(env_unit_handling or base.get("unitHandling") or "VERIFY")
    nan_handling = str(env_nan_handling or base.get("nanHandling") or "OFF")
    language = str(env_language or base.get("language") or "FASTEXPR")

    if env_visualization is not None:
        visualization = env_visualization.strip().lower() in {"1", "true", "yes", "on"}
    else:
        visualization = bool(base.get("visualization", False))

    return ResearchProfile(
        inst,
        region,
        universe,
        delay,
        decay,
        neutralization,
        truncation,
        pasteurization,
        unit_handling,
        nan_handling,
        language,
        visualization,
    )


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
