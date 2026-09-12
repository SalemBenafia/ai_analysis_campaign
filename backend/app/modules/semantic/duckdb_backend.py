"""
app/modules/semantic/duckdb_backend.py
========================================
Fallback engine: compiles a validated SemanticQuery to safe SQL over the
local DuckDB table (original column names). Used when Cube is unreachable,
when SEMANTIC_ENGINE=duckdb, and by report generation. Raw-column measures,
row-level formula metrics and OHLC (candlestick) queries always run here —
the generated Cube schema only knows aggregated members.

Produces the same row shape as the Cube path after normalization: keys are
semantic member names.
"""
from __future__ import annotations

import re
from typing import Any

import structlog

from app.modules.analytics.sql_builder import quote_table
from app.modules.semantic.formula import FormulaError, compile_formula_sql
from app.modules.semantic.registry import Member, MemberCatalog, UnknownMemberError
from app.modules.semantic.schemas import SemanticQuery

logger = structlog.get_logger()

_SQL_OPS = {"equals": "=", "notEquals": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def _quote(col: str) -> str:
    return '"' + col.replace('"', '""') + '"'


def _is_row_level(member: Member | None) -> bool:
    """Row-level member: a raw column measure OR a row-level formula metric.
    Selected without aggregation in detail-mode queries and never mixed with
    aggregated measures in the same query."""
    return member is not None and member.row_level


def _row_level_sql(member: Member, catalog: MemberCatalog) -> str:
    """SQL for a row-level member inside a detail query's SELECT / WHERE."""
    if member.kind == "computed" and member.expression:
        return _compile_expression_local(member.expression, catalog)
    return _quote(member.column or member.name)


def _measure_sql(member: Member, catalog: MemberCatalog) -> str:
    if member.agg == "COUNT":
        return "COUNT(*)"
    if member.kind == "measure" and member.column:
        if member.agg is None:
            raise UnknownMemberError(
                f"{member.name!r} is a raw column — it cannot be mixed with aggregated measures"
            )
        return f"{member.agg}({_quote(member.column)})"
    if member.kind == "computed" and member.expression:
        return _compile_expression_local(member.expression, catalog)
    raise UnknownMemberError(f"Cannot compile measure {member.name!r}")


def _compile_expression_local(expression: dict, catalog: MemberCatalog) -> str:
    """Compile a structured metric expression using ORIGINAL column names."""
    sem_to_orig = {
        m.semantic_column: m.column
        for m in list(catalog.dimensions.values()) + list(catalog.measures.values())
        if m.semantic_column and m.column
    }

    def part_sql(part: dict) -> str:
        agg = str(part.get("agg", "sum")).upper()
        if agg not in ("SUM", "AVG", "MIN", "MAX", "COUNT"):
            raise UnknownMemberError(f"Aggregation not allowed: {agg!r}")
        sem_col = str(part.get("column", ""))
        orig = sem_to_orig.get(sem_col, sem_col)
        return f"{agg}({_quote(orig)})"

    kind = expression.get("type")
    if kind == "ratio":
        num_sql = part_sql(expression["numerator"])
        den_sql = part_sql(expression["denominator"])
        multiplier = expression.get("multiplier", 1)
        if multiplier and multiplier != 1:
            num_sql = f"{num_sql} * {float(multiplier)}"
        return f"({num_sql}) / NULLIF({den_sql}, 0)"
    if kind == "aggregate":
        return part_sql(expression)
    if kind == "formula":
        try:
            return compile_formula_sql(
                expression.get("root") or {},
                lambda column: _quote(sem_to_orig.get(column, column)),
            )
        except FormulaError as e:
            raise UnknownMemberError(str(e)) from e
    raise UnknownMemberError(f"Unsupported expression type: {kind!r}")


def _parse_relative_range(date_range: str) -> int | None:
    match = re.fullmatch(r"last\s+(\d+)\s+days?", date_range.strip().lower())
    return int(match.group(1)) if match else None


def _apply_filters(
    query: SemanticQuery,
    catalog: MemberCatalog,
    measure_sql: dict[str, str],
    where_clauses: list[str],
    having_clauses: list[str],
    params: list[Any],
    detail_mode: bool = False,
) -> None:
    """Dimension and raw/row-level filters go to WHERE, aggregated to HAVING."""
    for f in query.filters:
        if f.member in catalog.dimensions:
            member = catalog.dimensions[f.member]
            target = _quote(member.column or f.member)
            bucket = where_clauses
        elif f.member in catalog.measures:
            member = catalog.measures[f.member]
            if _is_row_level(member):
                target = _row_level_sql(member, catalog)
                bucket = where_clauses
            elif detail_mode:
                raise UnknownMemberError(
                    f"Cannot filter on aggregated measure {f.member!r} in a raw-column query"
                )
            else:
                target = measure_sql.get(f.member) or _measure_sql(member, catalog)
                bucket = having_clauses
        else:
            raise UnknownMemberError(f"Unknown filter member: {f.member!r}")

        if f.operator in ("set", "notSet"):
            bucket.append(f"{target} IS {'NOT ' if f.operator == 'set' else ''}NULL")
        elif f.operator == "contains":
            bucket.append(f"{target} ILIKE ?")
            params.append(f"%{f.values[0] if f.values else ''}%")
        elif f.operator in ("equals", "notEquals") and len(f.values) > 1:
            placeholders = ", ".join("?" for _ in f.values)
            neg = "NOT " if f.operator == "notEquals" else ""
            bucket.append(f"{target} {neg}IN ({placeholders})")
            params.extend(f.values)
        else:
            if f.operator not in _SQL_OPS:
                raise UnknownMemberError(f"Operator not allowed: {f.operator!r}")
            if not f.values:
                raise UnknownMemberError(f"Filter on {f.member!r} has no value")
            bucket.append(f"{target} {_SQL_OPS[f.operator]} ?")
            params.append(f.values[0])


def _apply_date_range(
    query: SemanticQuery,
    catalog: MemberCatalog,
    where_clauses: list[str],
    params: list[Any],
) -> None:
    if not (query.time_dimension and query.date_range):
        return
    member = catalog.dimensions[query.time_dimension]
    col = _quote(member.column or query.time_dimension)
    if isinstance(query.date_range, list) and len(query.date_range) == 2:
        where_clauses.append(
            f"CAST({col} AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)"
        )
        params.extend(query.date_range)
    elif isinstance(query.date_range, str):
        days = _parse_relative_range(query.date_range)
        if days:
            where_clauses.append(
                f"CAST({col} AS DATE) >= current_date - INTERVAL {int(days)} DAY"
            )


def compile_semantic_sql(
    query: SemanticQuery, catalog: MemberCatalog, table_name: str
) -> tuple[str, list[Any]]:
    """Returns (sql, params). Every member must already exist in the catalog."""
    if getattr(query, "mode", "auto") == "ohlc":
        return compile_ohlc_sql(query, catalog, table_name)

    raw_members: list[Member] = []
    agg_names: list[str] = []
    for m in query.measures:
        member = catalog.measures.get(m)
        if member is None:
            raise UnknownMemberError(f"Unknown measure: {m!r}")
        if _is_row_level(member):
            raw_members.append(member)
        else:
            agg_names.append(m)
    if raw_members and agg_names:
        raise UnknownMemberError(
            f"Cannot mix raw columns (e.g. {raw_members[0].name!r}) with aggregated "
            f"measures (e.g. {agg_names[0]!r}) in one query"
        )
    # Detail mode: raw row-level values, no aggregation, no GROUP BY. This is
    # the real-time raw-tracking path (e.g. a line of raw spend over time).
    detail_mode = bool(raw_members)

    select_parts: list[str] = []
    group_parts: list[str] = []
    params: list[Any] = []

    for d in query.dimensions:
        member = catalog.dimensions.get(d)
        if member is None or not member.column:
            raise UnknownMemberError(f"Unknown dimension: {d!r}")
        select_parts.append(f"{_quote(member.column)} AS {_quote(d)}")
        if not detail_mode:
            group_parts.append(_quote(member.column))

    if query.time_dimension:
        member = catalog.dimensions.get(query.time_dimension)
        if member is None or member.type != "time" or not member.column:
            raise UnknownMemberError(f"Unknown time dimension: {query.time_dimension!r}")
        if detail_mode:
            # Full-resolution raw timestamp so the raw trace keeps its real
            # granularity (granularity truncation only applies to aggregates).
            select_parts.append(
                f"CAST({_quote(member.column)} AS VARCHAR) AS {_quote(query.time_dimension)}"
            )
        else:
            gran = query.granularity or "day"
            if gran not in ("day", "week", "month"):
                raise UnknownMemberError(f"Granularity not allowed: {gran!r}")
            expr = f"DATE_TRUNC('{gran}', {_quote(member.column)})"
            select_parts.append(f"CAST({expr} AS VARCHAR) AS {_quote(query.time_dimension)}")
            group_parts.append(expr)

    measure_sql: dict[str, str] = {}
    if detail_mode:
        for member in raw_members:
            select_parts.append(f"{_row_level_sql(member, catalog)} AS {_quote(member.name)}")
    else:
        for m in agg_names:
            member = catalog.measures[m]
            sql_expr = _measure_sql(member, catalog)
            measure_sql[m] = sql_expr
            select_parts.append(f"{sql_expr} AS {_quote(m)}")

    if not select_parts:
        raise UnknownMemberError("Query selects nothing")

    where_clauses: list[str] = []
    having_clauses: list[str] = []
    _apply_filters(
        query, catalog, measure_sql, where_clauses, having_clauses, params,
        detail_mode=detail_mode,
    )
    _apply_date_range(query, catalog, where_clauses, params)

    sql = f"SELECT {', '.join(select_parts)} FROM {quote_table(table_name)}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    if group_parts:
        sql += " GROUP BY " + ", ".join(group_parts)
    if having_clauses:
        sql += " HAVING " + " AND ".join(having_clauses)

    if query.order:
        order_parts = []
        for m, direction in query.order.items():
            catalog.get(m)
            order_parts.append(f"{_quote(m)} {'ASC' if direction == 'asc' else 'DESC'}")
        sql += " ORDER BY " + ", ".join(order_parts)
    elif detail_mode and query.time_dimension:
        # Default a raw time trace to chronological order for a sensible line.
        member = catalog.dimensions[query.time_dimension]
        sql += f" ORDER BY {_quote(member.column or query.time_dimension)} ASC"

    limit = max(1, min(int(query.limit or 500), 5000))
    sql += f" LIMIT {limit}"
    return sql, params


def compile_ohlc_sql(
    query: SemanticQuery, catalog: MemberCatalog, table_name: str
) -> tuple[str, list[Any]]:
    """
    OHLC aggregation for candlestick charts: per time bucket, open/close are
    the first/last values ordered by timestamp — with insertion order (rowid)
    breaking ties, so date-only columns (where every row in a day bucket has
    the same timestamp) still yield distinct, deterministic open and close.
    High/low are max/min. Requires exactly one raw column measure + time
    dimension + granularity.
    """
    if len(query.measures) != 1:
        raise UnknownMemberError("Candlestick needs exactly one raw measure")
    member = catalog.measures.get(query.measures[0])
    if member is None or not member.row_level or member.kind != "measure" or not member.column:
        raise UnknownMemberError(
            f"Candlestick needs a raw column measure (e.g. 'spend'), got {query.measures[0]!r}"
        )
    if query.dimensions:
        raise UnknownMemberError("Candlestick does not support extra dimensions")
    if not query.time_dimension:
        raise UnknownMemberError("Candlestick needs a time dimension")
    time_member = catalog.dimensions.get(query.time_dimension)
    if time_member is None or time_member.type != "time" or not time_member.column:
        raise UnknownMemberError(f"Unknown time dimension: {query.time_dimension!r}")
    gran = query.granularity or ""
    if gran not in ("day", "week", "month"):
        raise UnknownMemberError("Candlestick needs a granularity (day, week or month)")

    time_col = _quote(time_member.column)
    value_col = _quote(member.column or "")
    bucket = f"DATE_TRUNC('{gran}', {time_col})"

    select_parts = [
        f"CAST({bucket} AS VARCHAR) AS {_quote(query.time_dimension)}",
        f'first({value_col} ORDER BY {time_col}, rowid) AS "open"',
        f'MAX({value_col}) AS "high"',
        f'MIN({value_col}) AS "low"',
        f'last({value_col} ORDER BY {time_col}, rowid) AS "close"',
    ]

    params: list[Any] = []
    where_clauses: list[str] = []
    having_clauses: list[str] = []
    _apply_filters(query, catalog, {}, where_clauses, having_clauses, params, detail_mode=True)
    _apply_date_range(query, catalog, where_clauses, params)

    sql = f"SELECT {', '.join(select_parts)} FROM {quote_table(table_name)}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += f" GROUP BY {bucket} ORDER BY 1 ASC"
    limit = max(1, min(int(query.limit or 500), 5000))
    sql += f" LIMIT {limit}"
    return sql, params


def preview_metric_value(
    expression: dict, catalog: MemberCatalog, table_name: str
) -> Any:
    """Evaluate a metric expression for the dialog live preview.

    Aggregate metrics collapse to a single value; a row-level formula returns
    the value for the first row (a representative sample).
    """
    sql = (
        f"SELECT {_compile_expression_local(expression, catalog)} AS value"
        f" FROM {quote_table(table_name)} LIMIT 1"
    )
    from app.modules.datasets.service import fetch_dicts, get_duckdb

    rows = fetch_dicts(get_duckdb().execute(sql))
    return rows[0]["value"] if rows else None


def run_semantic_query_duckdb(
    query: SemanticQuery, catalog: MemberCatalog, table_name: str
) -> list[dict[str, Any]]:
    from app.modules.datasets.service import fetch_dicts, get_duckdb

    sql, params = compile_semantic_sql(query, catalog, table_name)
    return fetch_dicts(get_duckdb().execute(sql, params))
