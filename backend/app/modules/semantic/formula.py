"""
app/modules/semantic/formula.py
=================================
Custom computed-metric formulas: a small recursive expression AST stored as
JSON (structured — never raw SQL from the user) and compiled to SQL by both
engines (Cube YAML and the local DuckDB backend).

Stored shape:  {"type": "formula", "root": <node>}

  node := {"type": "binary", "op": "+"|"-"|"*"|"/", "left": node, "right": node}
        | {"type": "agg", "agg": "sum"|"avg"|"min"|"max"|"count"|"count_distinct"|"none",
           "column": "<semantic column>"}
        | {"type": "literal", "value": <number>}
        | {"type": "ref", "measure": "<member name>"}   # KPI definitions only

"none" means the raw column value (no aggregation). A formula that uses any
"none" term is *row-level*: it produces one value per row, runs only on the
DuckDB detail path, and cannot be mixed with real aggregations (SUM/AVG/…) —
just like a raw column measure. Everything else is a normal aggregate metric.

The engines differ only in how a column name resolves to a quoted SQL
identifier, so the compiler takes a resolve_column callback. Division always
compiles to NULLIF-guarded SQL; parenthesization is inherent to the tree.
"""
from __future__ import annotations

from typing import Annotated, Callable, Iterator, Literal, Mapping, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

FORMULA_AGGS = ("sum", "avg", "min", "max", "count", "count_distinct", "none")
# A flat N-term row folds into a left-deep binary tree of depth ~N, so the
# depth cap must comfortably exceed the per-row term count; MAX_NODES is the
# real size limit, depth only guards recursion.
MAX_DEPTH = 32
MAX_NODES = 50


class FormulaError(ValueError):
    """A formula failed validation or compilation."""


class FormulaAgg(BaseModel):
    type: Literal["agg"]
    agg: Literal["sum", "avg", "min", "max", "count", "count_distinct", "none"]
    column: str


class FormulaLiteral(BaseModel):
    type: Literal["literal"]
    value: float


class FormulaRef(BaseModel):
    type: Literal["ref"]
    measure: str


class FormulaBinary(BaseModel):
    type: Literal["binary"]
    op: Literal["+", "-", "*", "/"]
    left: "FormulaNode"
    right: "FormulaNode"


FormulaNode = Annotated[
    Union[FormulaBinary, FormulaAgg, FormulaLiteral, FormulaRef],
    Field(discriminator="type"),
]

FormulaBinary.model_rebuild()

_NODE_ADAPTER: TypeAdapter = TypeAdapter(FormulaNode)

_Node = Union[FormulaBinary, FormulaAgg, FormulaLiteral, FormulaRef]


def parse_formula(root: dict) -> _Node:
    """Parse + structurally validate a formula node dict. Raises FormulaError."""
    if not isinstance(root, dict):
        raise FormulaError("Formula root must be an object.")
    try:
        return _NODE_ADAPTER.validate_python(root)
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        raise FormulaError(f"Malformed formula: {first.get('msg', 'invalid node')}") from e


def _walk(node: _Node, depth: int = 1) -> Iterator[tuple[_Node, int]]:
    yield node, depth
    if isinstance(node, FormulaBinary):
        yield from _walk(node.left, depth + 1)
        yield from _walk(node.right, depth + 1)


def iter_formula_columns(root: dict) -> Iterator[str]:
    """Yield every column referenced by agg nodes in a formula."""
    for node, _ in _walk(parse_formula(root)):
        if isinstance(node, FormulaAgg):
            yield node.column


def formula_is_row_level(root: dict) -> bool:
    """True if any term uses the raw ("none") aggregation — a row-level formula."""
    for node, _ in _walk(parse_formula(root)):
        if isinstance(node, FormulaAgg) and node.agg == "none":
            return True
    return False


def expression_is_row_level(expression: dict | None) -> bool:
    """True if a stored metric expression is a row-level formula (raw values).

    Row-level metrics run only on the DuckDB detail path and behave like raw
    column measures; the Cube schema never receives them.
    """
    if not expression or expression.get("type") != "formula":
        return False
    try:
        return formula_is_row_level(expression.get("root") or {})
    except FormulaError:
        return False


def validate_formula(
    root: dict,
    valid_columns: set[str] | None = None,
    *,
    allow_refs: bool = False,
    valid_refs: set[str] | None = None,
) -> None:
    """
    Full validation of a formula: structure, size limits, column existence,
    and ref policy (refs are only legal in KPI definitions, where they must
    point at the query's selected measures). Raises FormulaError.
    """
    parsed = parse_formula(root)

    count = 0
    has_operand = False
    has_raw = False   # a "none" term (raw column value)
    has_agg = False   # a real aggregation (SUM/AVG/…)
    for node, depth in _walk(parsed):
        count += 1
        if count > MAX_NODES:
            raise FormulaError(f"Formula too large (max {MAX_NODES} terms).")
        if depth > MAX_DEPTH:
            raise FormulaError(f"Formula too deeply nested (max depth {MAX_DEPTH}).")
        if isinstance(node, FormulaAgg):
            has_operand = True
            if node.agg == "none":
                has_raw = True
            else:
                has_agg = True
            if valid_columns is not None and node.column not in valid_columns:
                raise FormulaError(f"Unknown column {node.column!r} in formula.")
        elif isinstance(node, FormulaRef):
            has_operand = True
            if not allow_refs:
                raise FormulaError("Measure references are not allowed in computed metrics.")
            if valid_refs is not None and node.measure not in valid_refs:
                raise FormulaError(f"Unknown measure {node.measure!r} in formula.")

    if not has_operand:
        raise FormulaError("Formula must reference at least one column or measure.")
    if has_raw and has_agg:
        raise FormulaError(
            "A formula can't mix raw column values with aggregations like SUM or AVG."
        )


def compile_formula_sql(
    root: dict,
    resolve_column: Callable[[str], str],
    *,
    allow_refs: bool = False,
    resolve_ref: Callable[[str], str] | None = None,
) -> str:
    """
    Compile a formula node to SQL. resolve_column maps a semantic column name
    to a quoted identifier (each engine supplies its own); resolve_ref maps a
    measure reference the same way when allow_refs is set.
    """
    def emit(node: _Node) -> str:
        if isinstance(node, FormulaBinary):
            left = emit(node.left)
            right = emit(node.right)
            if node.op == "/":
                return f"({left} / NULLIF({right}, 0))"
            return f"({left} {node.op} {right})"
        if isinstance(node, FormulaAgg):
            ident = resolve_column(node.column)
            if node.agg == "none":
                return ident  # raw column value (row-level term)
            if node.agg == "count_distinct":
                return f"COUNT(DISTINCT {ident})"
            return f"{node.agg.upper()}({ident})"
        if isinstance(node, FormulaLiteral):
            return repr(float(node.value))
        if not allow_refs or resolve_ref is None:
            raise FormulaError("Measure references are not allowed in computed metrics.")
        return resolve_ref(node.measure)

    return emit(parse_formula(root))


def evaluate_formula(root: dict, refs: Mapping[str, float | None]) -> float | None:
    """
    Evaluate a ref/literal/binary formula over already-aggregated values
    (KPI custom calculations). agg nodes cannot be evaluated here. Division
    by zero and missing refs yield None, mirroring SQL NULL semantics.
    """
    def ev(node: _Node) -> float | None:
        if isinstance(node, FormulaBinary):
            left = ev(node.left)
            right = ev(node.right)
            if left is None or right is None:
                return None
            if node.op == "+":
                return left + right
            if node.op == "-":
                return left - right
            if node.op == "*":
                return left * right
            return None if right == 0 else left / right
        if isinstance(node, FormulaLiteral):
            return float(node.value)
        if isinstance(node, FormulaRef):
            value = refs.get(node.measure)
            return None if value is None else float(value)
        raise FormulaError("Aggregations cannot be evaluated over query results.")

    return ev(parse_formula(root))
