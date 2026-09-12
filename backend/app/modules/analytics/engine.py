"""
app/modules/analytics/engine.py
=================================
Analytics Engine — DuckDB-powered KPI calculations.
Performs aggregations, group-by, time-series, comparisons.
The AI Copilot delegates computation here instead of using the LLM for math.

All SQL is built through sql_builder: identifiers are validated against the
dataset's real column set and every value is a bound parameter.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.modules.analytics.sql_builder import (
    compile_filters,
    quote_ident,
    quote_table,
    validate_agg,
    validate_order,
    validate_truncate,
)
from app.modules.datasets.service import fetch_dicts, get_duckdb

logger = structlog.get_logger()


def compute_kpis(
    table_name: str, metric_cols: list[str], allowed_columns: set[str]
) -> dict[str, float]:
    """Compute SUM and AVG for all numeric metric columns."""
    if not metric_cols:
        return {}
    conn = get_duckdb()
    aggs = ", ".join(
        f'SUM({quote_ident(c, allowed_columns)}) AS "{c}_sum", '
        f'AVG({quote_ident(c, allowed_columns)}) AS "{c}_avg"'
        for c in metric_cols
    )
    try:
        cursor = conn.execute(f"SELECT {aggs} FROM {quote_table(table_name)}")
        desc = cursor.description
        row = cursor.fetchone()
        return {desc[i][0]: (row[i] or 0.0) for i in range(len(desc))}
    except Exception as e:
        logger.error("KPI computation failed", table=table_name, error=str(e))
        return {}


def group_by_metric(
    table_name: str,
    dimension: str,
    metric: str,
    allowed_columns: set[str],
    agg: str = "SUM",
    filters: list[dict] | None = None,
    limit: int = 50,
    order: str = "DESC",
) -> list[dict[str, Any]]:
    """Group a metric by a dimension with optional filters."""
    conn = get_duckdb()
    dim = quote_ident(dimension, allowed_columns)
    met = quote_ident(metric, allowed_columns)
    agg_fn = validate_agg(agg)
    direction = validate_order(order)
    where, params = compile_filters(filters, allowed_columns)
    limit = max(1, min(int(limit), 5000))
    sql = f"""
    SELECT {dim} AS {dim}, {agg_fn}({met}) AS value
    FROM {quote_table(table_name)}
    {where}
    GROUP BY {dim}
    ORDER BY value {direction}
    LIMIT {limit}
    """
    try:
        return fetch_dicts(conn.execute(sql, params))
    except Exception as e:
        logger.error("group_by failed", error=str(e))
        return []


def time_series(
    table_name: str,
    date_col: str,
    metric: str,
    allowed_columns: set[str],
    agg: str = "SUM",
    truncate: str = "day",
    filters: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Time-series aggregation truncated to day/week/month."""
    conn = get_duckdb()
    date_q = quote_ident(date_col, allowed_columns)
    met = quote_ident(metric, allowed_columns)
    agg_fn = validate_agg(agg)
    trunc = validate_truncate(truncate)
    where, params = compile_filters(filters, allowed_columns)
    sql = f"""
    SELECT DATE_TRUNC('{trunc}', {date_q}) AS period, {agg_fn}({met}) AS value
    FROM {quote_table(table_name)}
    {where}
    GROUP BY period
    ORDER BY period ASC
    """
    try:
        return fetch_dicts(conn.execute(sql, params))
    except Exception as e:
        logger.error("time_series failed", error=str(e))
        return []


def detect_anomalies(
    table_name: str,
    metric: str,
    allowed_columns: set[str],
    threshold: float = 2.0,
) -> list[dict[str, Any]]:
    """
    Z-score based anomaly detection.
    Returns rows where |z-score| > threshold.
    """
    conn = get_duckdb()
    met = quote_ident(metric, allowed_columns)
    threshold = float(threshold)
    table = quote_table(table_name)
    sql = f"""
    WITH stats AS (
        SELECT AVG({met}) AS mean, STDDEV({met}) AS std
        FROM {table}
    )
    SELECT *, ({met} - stats.mean) / NULLIF(stats.std, 0) AS z_score
    FROM {table}, stats
    WHERE ABS(({met} - stats.mean) / NULLIF(stats.std, 0)) > ?
    ORDER BY ABS(({met} - stats.mean) / NULLIF(stats.std, 0)) DESC
    LIMIT 20
    """
    try:
        return fetch_dicts(conn.execute(sql, [threshold]))
    except Exception as e:
        logger.error("anomaly detection failed", error=str(e))
        return []


def period_comparison(
    table_name: str,
    date_col: str,
    metric: str,
    period_a: tuple[str, str],
    period_b: tuple[str, str],
    allowed_columns: set[str],
    agg: str = "SUM",
) -> dict[str, Any]:
    """Compare metric between two date ranges. Returns delta and % change."""
    conn = get_duckdb()
    date_q = quote_ident(date_col, allowed_columns)
    met = quote_ident(metric, allowed_columns)
    agg_fn = validate_agg(agg)
    table = quote_table(table_name)

    def _query(start: str, end: str) -> float:
        row = conn.execute(
            f"SELECT {agg_fn}({met}) FROM {table} "
            f"WHERE CAST({date_q} AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)",
            [start, end],
        ).fetchone()
        return float(row[0] or 0)

    val_a = _query(*period_a)
    val_b = _query(*period_b)
    delta = val_b - val_a
    pct_change = (delta / val_a * 100) if val_a != 0 else None

    return {
        "period_a": {"range": list(period_a), "value": val_a},
        "period_b": {"range": list(period_b), "value": val_b},
        "delta": delta,
        "pct_change": round(pct_change, 2) if pct_change is not None else None,
        "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
    }
