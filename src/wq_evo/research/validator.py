from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUM_RE = re.compile(r"(?<![A-Za-z_])[+-]?\d+(?:\.\d+)?")


def nesting_depth(s: str) -> int:
    depth = best = 0
    for ch in s:
        if ch == "(":
            depth += 1
            best = max(best, depth)
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return 999
    return best


def validate_expression(expression: str, *, allowed_operators: Iterable[str], allowed_fields: Iterable[str],
                        max_chars: int = 300, max_depth: int = 12, max_numeric_constants: int = 12) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    s = expression.strip()
    if not s:
        return ValidationResult(False, ["empty expression"], [])
    if len(s) > max_chars:
        errors.append(f"expression too long ({len(s)}>{max_chars})")
    if nesting_depth(s) > max_depth:
        errors.append("nesting depth exceeds safety limit")
    if s.count(";") > 0:
        errors.append("statement separators are not permitted")
    for pat in ("__", "import ", "exec(", "eval(", "http://", "https://", "subprocess", "os.", "system("):
        if pat.lower() in s.lower():
            errors.append(f"forbidden token/pattern: {pat}")
    if len(NUM_RE.findall(s)) > max_numeric_constants:
        errors.append("too many numeric constants")

    balanced = 0
    for ch in s:
        if ch == "(": balanced += 1
        elif ch == ")":
            balanced -= 1
            if balanced < 0:
                errors.append("unbalanced parentheses")
                break
    if balanced != 0:
        errors.append("unbalanced parentheses")

    op_set = {x.lower() for x in allowed_operators}
    field_set = {x.lower() for x in allowed_fields}
    identifiers = {x.lower() for x in IDENT_RE.findall(s)}
    # Function calls count as operators; other identifiers count as fields / group labels.
    functions = {m.group(1).lower() for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", s)}
    unknown_ops = sorted(x for x in functions if x not in op_set)
    if unknown_ops:
        errors.append("unknown operators: " + ", ".join(unknown_ops[:8]))

    # Remove operators and common literals/keywords from identifier candidates.
    residual = identifiers - functions - {"and", "or", "if", "else", "true", "false"}
    unknown_fields = sorted(x for x in residual if x not in field_set)
    if unknown_fields:
        warnings.append("unknown identifiers pending platform validation: " + ", ".join(unknown_fields[:8]))

    return ValidationResult(not errors, errors, warnings)
