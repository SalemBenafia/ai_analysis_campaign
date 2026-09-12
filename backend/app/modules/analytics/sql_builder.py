"""
app/modules/analytics/sql_builder.py
=====================================
Safe SQL construction for DuckDB.

Every identifier is checked against the dataset's actual column set before it
is quoted, every value travels as a bound parameter, and free-form SQL is
parsed with sqlglot and restricted to a single SELECT over the dataset's own
table. Nothing user-controlled is ever interpolated raw into SQL text.
"""
from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import expressions as exp

AGG_ALLOWLIST = {"SUM", "AVG", "MIN", "MAX", "COUNT", "MEDIAN"}
TRUNC_ALLOWLIST = {"day", "week", "month"}
ORDER_ALLOWLIST = {"ASC", "DESC"}

FILTER_OPS = {
    "=": "=",
    "!=": "!=",
    ">": ">",
    "<": "<",
    ">=": ">=",
    "<=": "<=",
    "equals": "=",
    "notEquals": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "contains": "ILIKE",
}


class UnsafeIdentifierError(ValueError):
    """Raised when an identifier is not part of the dataset schema."""


class UnsafeSQLError(ValueError):
    """Raised when free-form SQL fails validation."""


def quote_ident(name: str, allowed: set[str]) -> str:
    """Quote a column name after verifying it exists in the dataset schema."""
    if name not in allowed:
        raise UnsafeIdentifierError(f"Unknown column: {name!r}")
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def quote_table(table_name: str) -> str:
    """Quote a DuckDB table name (ds_<slug>_<id8> — server-generated)."""
    escaped = table_name.replace('"', '""')
    return f'"{escaped}"'


def validate_agg(agg: str) -> str:
    up = (agg or "SUM").upper()
    if up not in AGG_ALLOWLIST:
        raise UnsafeSQLError(f"Aggregation not allowed: {agg!r}")
    return up


def validate_truncate(truncate: str) -> str:
    low = (truncate or "day").lower()
    if low not in TRUNC_ALLOWLIST:
        raise UnsafeSQLError(f"Granularity not allowed: {truncate!r}")
    return low


def validate_order(order: str) -> str:
    up = (order or "DESC").upper()
    if up not in ORDER_ALLOWLIST:
        raise UnsafeSQLError(f"Order not allowed: {order!r}")
    return up


def compile_filters(
    filters: list[dict] | None, allowed: set[str]
) -> tuple[str, list[Any]]:
    """
    Compile filter dicts into a parameterized WHERE clause.

    Accepts both legacy shape {field, operator, value} and semantic shape
    {member, operator, values}. Returns ("WHERE ...", params) or ("", []).
    """
    if not filters:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []
    for f in filters:
        field = f.get("field") or f.get("member") or ""
        op_key = str(f.get("operator", "="))
        if op_key not in FILTER_OPS:
            raise UnsafeSQLError(f"Filter operator not allowed: {op_key!r}")
        op = FILTER_OPS[op_key]

        col = quote_ident(field, allowed)

        if op_key in ("set", "notSet"):
            clauses.append(f"{col} IS {'NOT ' if op_key == 'set' else ''}NULL")
            continue

        value = f.get("value")
        if value is None:
            values = f.get("values") or []
            value = values[0] if values else None
        if value is None:
            raise UnsafeSQLError(f"Filter on {field!r} has no value")

        if op == "ILIKE":
            clauses.append(f"{col} ILIKE ?")
            params.append(f"%{value}%")
        else:
            clauses.append(f"{col} {op} ?")
            params.append(value)

    return "WHERE " + " AND ".join(clauses), params


_FORBIDDEN_NODES = tuple(
    node
    for name in (
        "Create", "Insert", "Update", "Delete", "Drop", "Alter", "AlterTable",
        "Attach", "Detach", "Copy", "Pragma", "Install", "Command", "Set",
        "Use", "Merge", "TruncateTable",
    )
    if (node := getattr(exp, name, None)) is not None
)


def validate_select(sql: str, allowed_table: str) -> str:
    """
    Validate free-form SQL: exactly one SELECT statement whose every table
    reference is the dataset's own table. Raises UnsafeSQLError otherwise.
    """
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except Exception as e:
        raise UnsafeSQLError(f"SQL could not be parsed: {e}") from e

    if len(statements) != 1 or statements[0] is None:
        raise UnsafeSQLError("Exactly one SQL statement is allowed.")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise UnsafeSQLError("Only SELECT statements are allowed.")

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeSQLError(f"Statement type not allowed: {type(node).__name__}")
        if isinstance(node, exp.Table):
            name = node.name
            # CTE aliases resolve as tables too — allow references to CTEs
            # defined inside this same statement.
            cte_names = {c.alias_or_name for c in stmt.find_all(exp.CTE)}
            if name != allowed_table and name not in cte_names:
                raise UnsafeSQLError(
                    f"Query may only reference the dataset table {allowed_table!r}."
                )

    return sql
