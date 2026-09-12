"""
app/modules/insights/engine.py
================================
Insight Discovery Engine — finds patterns, anomalies, trends, opportunities.
Produces structured findings that the AI Copilot narrates in natural language.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.modules.analytics.engine import detect_anomalies, group_by_metric, time_series
from app.modules.analytics.sql_builder import quote_ident, quote_table
from app.modules.datasets.service import get_duckdb

logger = structlog.get_logger()


def discover_top_performers(
    table_name: str, dimension: str, metric: str, allowed: set[str], top_n: int = 5
) -> list[dict]:
    rows = group_by_metric(table_name, dimension, metric, allowed, "SUM", limit=top_n, order="DESC")
    return [{"rank": i + 1, **r} for i, r in enumerate(rows)]


def discover_bottom_performers(
    table_name: str, dimension: str, metric: str, allowed: set[str], top_n: int = 5
) -> list[dict]:
    rows = group_by_metric(table_name, dimension, metric, allowed, "SUM", limit=top_n, order="ASC")
    return [{"rank": i + 1, **r} for i, r in enumerate(rows)]


def discover_anomalies(
    table_name: str, metric: str, allowed: set[str], threshold: float = 2.0
) -> list[dict]:
    return detect_anomalies(table_name, metric, allowed, threshold)


def discover_trend(
    table_name: str, date_col: str, metric: str, allowed: set[str]
) -> dict[str, Any]:
    """Determine overall trend direction for a metric over time."""
    rows = time_series(table_name, date_col, metric, allowed, "SUM", "day")
    if len(rows) < 2:
        return {"trend": "insufficient_data", "rows": rows}

    values = [r["value"] for r in rows if r["value"] is not None]
    if not values:
        return {"trend": "no_data", "rows": rows}

    first_half = sum(values[: len(values) // 2]) / (len(values) // 2)
    second_half = sum(values[len(values) // 2 :]) / (len(values) - len(values) // 2)
    pct = (second_half - first_half) / first_half * 100 if first_half else 0

    trend = "up" if pct > 5 else "down" if pct < -5 else "stable"
    return {"trend": trend, "pct_change": round(pct, 2), "rows": rows}


def discover_correlations(
    table_name: str, metric_a: str, metric_b: str, allowed: set[str]
) -> dict[str, Any]:
    """Pearson correlation between two metrics."""
    conn = get_duckdb()
    try:
        a = quote_ident(metric_a, allowed)
        b = quote_ident(metric_b, allowed)
        row = conn.execute(
            f"SELECT CORR({a}, {b}) AS corr FROM {quote_table(table_name)}"
        ).fetchone()
        corr = float(row[0]) if row and row[0] is not None else None
        if corr is None:
            label = "unknown"
        elif corr > 0.7:
            label = "strong_positive"
        elif corr > 0.3:
            label = "moderate_positive"
        elif corr < -0.7:
            label = "strong_negative"
        elif corr < -0.3:
            label = "moderate_negative"
        else:
            label = "weak"
        return {"metric_a": metric_a, "metric_b": metric_b, "correlation": corr, "label": label}
    except Exception as e:
        return {"error": str(e)}


def run_full_discovery(
    table_name: str,
    metric_cols: list[str],
    dimension_cols: list[str],
    allowed_columns: set[str],
    date_col: str | None = None,
) -> dict[str, Any]:
    """
    Run all insight discovery algorithms and return a structured findings report.
    Called by the AI Copilot when the user asks for an automated analysis.
    """
    findings: dict[str, Any] = {}

    if metric_cols and dimension_cols:
        primary_metric = metric_cols[0]
        primary_dim = dimension_cols[0]
        findings["top_performers"] = discover_top_performers(
            table_name, primary_dim, primary_metric, allowed_columns
        )
        findings["bottom_performers"] = discover_bottom_performers(
            table_name, primary_dim, primary_metric, allowed_columns
        )
        findings["anomalies"] = discover_anomalies(table_name, primary_metric, allowed_columns)

        if len(metric_cols) >= 2:
            findings["correlation"] = discover_correlations(
                table_name, metric_cols[0], metric_cols[1], allowed_columns
            )

    if date_col and metric_cols:
        findings["trend"] = discover_trend(table_name, date_col, metric_cols[0], allowed_columns)

    return findings
