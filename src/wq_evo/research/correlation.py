from __future__ import annotations

from datetime import datetime
from typing import Any
import numpy as np


def decode_recordset(recordset: dict[str, Any]) -> list[dict[str, Any]]:
    schema = recordset.get("schema") or {}
    props = schema.get("properties") or []
    names = [str(p.get("name")) for p in props] if isinstance(props, list) else []
    out: list[dict[str, Any]] = []
    for row in recordset.get("records") or []:
        if not isinstance(row, list):
            continue
        out.append({names[i]: row[i] for i in range(min(len(names), len(row)))})
    return out


def aligned_daily_returns(new_recordset: dict[str, Any], old_recordset: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Align by date before differencing cumulative PnL; never correlate cumulative PnL directly."""
    n = decode_recordset(new_recordset)
    o = decode_recordset(old_recordset)
    nm = {str(r.get("date")): float(r.get("pnl", r.get("cum_pnl", r.get("returns")))) for r in n if r.get("date") is not None}
    om = {str(r.get("date")): float(r.get("pnl", r.get("cum_pnl", r.get("returns")))) for r in o if r.get("date") is not None}
    dates = sorted(set(nm) & set(om))
    if len(dates) < 30:
        return np.array([]), np.array([])
    nv = np.array([nm[d] for d in dates], dtype=float)
    ov = np.array([om[d] for d in dates], dtype=float)
    return np.diff(nv), np.diff(ov)


def pearson_abs(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 29 or len(a) != len(b):
        return None
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(abs(np.corrcoef(a, b)[0, 1]))
