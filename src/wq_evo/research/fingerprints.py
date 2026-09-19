from __future__ import annotations

import hashlib
import re
from typing import Any


def canonical_expression(expr: str) -> str:
    s = re.sub(r"\s+", "", expr or "")
    return s


def fingerprint(expression: str | None, settings: dict[str, Any], lane: str) -> str:
    raw = f"{lane}|{canonical_expression(expression or '')}|" + "|".join(
        f"{k}={settings.get(k)}" for k in sorted(settings)
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def structural_signature(expression: str) -> str:
    """Coarse AST-like signature for cheap deduplication before simulation."""
    s = canonical_expression(expression)
    s = re.sub(r"\d+(?:\.\d+)?", "N", s)
    s = re.sub(r"[A-Za-z_][A-Za-z0-9_]*", lambda m: m.group(0).lower(), s)
    return s
