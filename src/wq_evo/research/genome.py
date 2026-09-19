from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .ontology import infer_field_traits


class ExpressionSyntaxError(ValueError):
    """Raised when an expression cannot be parsed by the controlled FASTEXPR grammar."""


@dataclass(frozen=True)
class ASTNode:
    kind: str
    value: str | float | None = None
    children: tuple["ASTNode", ...] = ()


@dataclass(frozen=True)
class FieldUse:
    field_id: str
    category: str | None = None
    dataset: str | None = None
    field_type: str | None = None
    coverage: float | None = None
    date_coverage: float | None = None
    alpha_count: int | None = None
    user_count: int | None = None
    traits: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlphaGenome:
    expression: str
    canonical_expression: str
    ast_signature: str
    fields: tuple[FieldUse, ...]
    operators: tuple[str, ...]
    groups: tuple[str, ...]
    constants: tuple[float, ...]
    windows: tuple[int, ...]
    node_count: int
    depth: int
    function_count: int
    binary_operator_count: int
    field_categories: tuple[str, ...]
    datasets: tuple[str, ...]
    semantic_traits: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "canonical_expression": self.canonical_expression,
            "ast_signature": self.ast_signature,
            "fields": [f.__dict__ for f in self.fields],
            "operators": list(self.operators),
            "groups": list(self.groups),
            "constants": list(self.constants),
            "windows": list(self.windows),
            "node_count": self.node_count,
            "depth": self.depth,
            "function_count": self.function_count,
            "binary_operator_count": self.binary_operator_count,
            "field_categories": list(self.field_categories),
            "datasets": list(self.datasets),
            "semantic_traits": list(self.semantic_traits),
        }


_TOKEN_RE = re.compile(
    r"\s*("
    r"(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>[+\-*/])"
    r"|(?P<lpar>\()"
    r"|(?P<rpar>\))"
    r"|(?P<comma>,)"
    r")"
)


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def _tokenize(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(expression):
        m = _TOKEN_RE.match(expression, pos)
        if not m:
            raise ExpressionSyntaxError(f"Unexpected token at character {pos}: {expression[pos:pos+20]!r}")
        pos = m.end()
        kind = "NUMBER" if m.group("number") else "IDENT" if m.group("ident") else m.lastgroup.upper()
        tokens.append(_Token(kind, m.group(m.lastgroup)))
    tokens.append(_Token("EOF", ""))
    return tokens


class _Parser:
    def __init__(self, expression: str):
        self.tokens = _tokenize(expression)
        self.i = 0

    def peek(self) -> _Token:
        return self.tokens[self.i]

    def take(self, kind: str | None = None) -> _Token:
        token = self.peek()
        if kind and token.kind != kind:
            raise ExpressionSyntaxError(f"Expected {kind}, got {token.kind} ({token.value!r})")
        self.i += 1
        return token

    def parse(self) -> ASTNode:
        node = self._parse_additive()
        if self.peek().kind != "EOF":
            raise ExpressionSyntaxError(f"Unexpected trailing token {self.peek().value!r}")
        return node

    def _parse_additive(self) -> ASTNode:
        node = self._parse_multiplicative()
        while self.peek().kind in {"OP"} and self.peek().value in {"+", "-"}:
            op = self.take("OP").value
            rhs = self._parse_multiplicative()
            node = ASTNode("binary", op, (node, rhs))
        return node

    def _parse_multiplicative(self) -> ASTNode:
        node = self._parse_unary()
        while self.peek().kind == "OP" and self.peek().value in {"*", "/"}:
            op = self.take("OP").value
            rhs = self._parse_unary()
            node = ASTNode("binary", op, (node, rhs))
        return node

    def _parse_unary(self) -> ASTNode:
        if self.peek().kind == "OP" and self.peek().value in {"+", "-"}:
            op = self.take("OP").value
            child = self._parse_unary()
            return ASTNode("unary", op, (child,))
        return self._parse_atom()

    def _parse_atom(self) -> ASTNode:
        token = self.peek()
        if token.kind == "NUMBER":
            self.take()
            return ASTNode("number", float(token.value))
        if token.kind == "IDENT":
            ident = self.take("IDENT").value
            if self.peek().kind == "LPAR":
                self.take("LPAR")
                args: list[ASTNode] = []
                if self.peek().kind != "RPAR":
                    while True:
                        args.append(self._parse_additive())
                        if self.peek().kind != "COMMA":
                            break
                        self.take("COMMA")
                self.take("RPAR")
                return ASTNode("call", ident.lower(), tuple(args))
            return ASTNode("identifier", ident)
        if token.kind == "LPAR":
            self.take("LPAR")
            node = self._parse_additive()
            self.take("RPAR")
            return node
        raise ExpressionSyntaxError(f"Expected expression atom, got {token.kind} ({token.value!r})")


def parse_expression(expression: str) -> ASTNode:
    """Parse the controlled arithmetic/function-call subset used by EvoForge.

    This is deliberately not Python evaluation and never executes the expression.
    """
    if not expression or not expression.strip():
        raise ExpressionSyntaxError("Expression is empty")
    return _Parser(expression).parse()


def _fmt_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".12g")


def canonical_from_ast(node: ASTNode) -> str:
    if node.kind == "number":
        return _fmt_number(float(node.value))
    if node.kind == "identifier":
        return str(node.value)
    if node.kind == "unary":
        return f"{node.value}{canonical_from_ast(node.children[0])}"
    if node.kind == "binary":
        return (
            f"({canonical_from_ast(node.children[0])}"
            f"{node.value}"
            f"{canonical_from_ast(node.children[1])})"
        )
    if node.kind == "call":
        args = ",".join(canonical_from_ast(x) for x in node.children)
        return f"{str(node.value).lower()}({args})"
    raise ExpressionSyntaxError(f"Unknown AST node kind {node.kind!r}")


def ast_signature(node: ASTNode) -> str:
    """Structure-only representation: field names and numeric constants are abstracted."""
    if node.kind == "number":
        return "N"
    if node.kind == "identifier":
        return "I"
    if node.kind == "unary":
        return f"U:{node.value}[{ast_signature(node.children[0])}]"
    if node.kind == "binary":
        return f"B:{node.value}[{ast_signature(node.children[0])},{ast_signature(node.children[1])}]"
    if node.kind == "call":
        return f"F:{str(node.value).lower()}[{','.join(ast_signature(x) for x in node.children)}]"
    raise ExpressionSyntaxError(f"Unknown AST node kind {node.kind!r}")


def _walk(node: ASTNode) -> Iterable[ASTNode]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _depth(node: ASTNode) -> int:
    if not node.children:
        return 1
    return 1 + max(_depth(x) for x in node.children)


def _field_map(field_catalog: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in field_catalog:
        fid = str(row.get("id") or "").strip()
        if fid:
            out[fid] = row
    return out


def build_genome(expression: str, field_catalog: Iterable[dict[str, Any]] = ()) -> AlphaGenome:
    ast = parse_expression(expression)
    nodes = list(_walk(ast))

    field_rows = _field_map(field_catalog)
    field_uses: list[FieldUse] = []
    operators: set[str] = set()
    groups: set[str] = set()
    constants: list[float] = []
    windows: list[int] = []
    categories: set[str] = set()
    datasets: set[str] = set()
    semantic_traits: set[str] = set()

    for node in nodes:
        if node.kind == "number":
            constants.append(float(node.value))
        elif node.kind == "identifier":
            if str(node.value).lower() in {"industry", "subindustry", "sector", "market"}:
                groups.add(str(node.value).lower())
            else:
                row = field_rows.get(str(node.value))
                if row is not None:
                    traits = tuple(sorted(infer_field_traits(row)))
                    field_uses.append(
                        FieldUse(
                            field_id=str(node.value),
                            category=_str_or_none(row.get("category")),
                            dataset=_str_or_none(row.get("dataset")),
                            field_type=_str_or_none(row.get("type")),
                            coverage=_num_or_none(row.get("coverage")),
                            date_coverage=_num_or_none(row.get("dateCoverage") or row.get("date_coverage")),
                            alpha_count=_int_or_none(row.get("alphaCount") or row.get("alpha_count")),
                            user_count=_int_or_none(row.get("userCount") or row.get("user_count")),
                            traits=traits,
                        )
                    )
                    if row.get("category"):
                        categories.add(str(row["category"]))
                    if row.get("dataset"):
                        datasets.add(str(row["dataset"]))
                    semantic_traits.update(traits)
        elif node.kind == "call":
            operators.add(str(node.value).lower())
            # In BRAIN-style time-series calls, the final numeric argument is commonly a window.
            if node.children and node.children[-1].kind == "number":
                w = float(node.children[-1].value)
                if w.is_integer() and 1 <= w <= 512:
                    windows.append(int(w))
        # binary/unary operators are represented in the AST but not treated as BRAIN functions.

    unique_fields: dict[str, FieldUse] = {x.field_id: x for x in field_uses}
    return AlphaGenome(
        expression=expression,
        canonical_expression=canonical_from_ast(ast),
        ast_signature=ast_signature(ast),
        fields=tuple(unique_fields[k] for k in sorted(unique_fields)),
        operators=tuple(sorted(operators)),
        groups=tuple(sorted(groups)),
        constants=tuple(sorted(set(constants))),
        windows=tuple(sorted(set(windows))),
        node_count=len(nodes),
        depth=_depth(ast),
        function_count=sum(n.kind == "call" for n in nodes),
        binary_operator_count=sum(n.kind == "binary" for n in nodes),
        field_categories=tuple(sorted(categories)),
        datasets=tuple(sorted(datasets)),
        semantic_traits=tuple(sorted(semantic_traits)),
    )


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _num_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None
