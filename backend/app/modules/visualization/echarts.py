"""
app/modules/visualization/echarts.py
======================================
Builds ECharts option JSON from rows + a chart spec. Single source of truth
for chart configs across insights, dashboards, and the copilot viz tool.
Dark "cyber" theme matching the frontend (accent #00d4ff).
"""
from __future__ import annotations

from typing import Any

import structlog

from app.modules.semantic.formula import FormulaError, evaluate_formula

logger = structlog.get_logger()

ACCENT = "#00d4ff"
_PALETTE = ["#00d4ff", "#a855f7", "#22c55e", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6"]

_AXIS_LABEL = {"color": "#94a3b8"}
_TITLE_STYLE = {"color": "#e2e8f0"}


def _base(title: str) -> dict[str, Any]:
    return {
        "title": {"text": title, "textStyle": _TITLE_STYLE} if title else {},
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis"},
        "legend": {"textStyle": _AXIS_LABEL, "top": "bottom"},
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "top": "15%", "containLabel": True},
        "color": _PALETTE,
    }


def build_echart_option(
    rows: list[dict],
    chart_type: str,
    x_field: str | None,
    y_fields: list[str],
    title: str = "",
    color_field: str | None = None,
    kpi: dict | None = None,
) -> dict[str, Any]:
    """
    rows: list of dict records.
    chart_type: bar | line | area | pie | scatter | table | kpi | candlestick
    x_field: category/time dimension (first dimension).
    y_fields: one or more measure keys.
    color_field: optional second dimension to break series by.
    kpi: optional {"expression": {...formula...}, "label": str} custom calculation.
    """
    chart_type = (chart_type or "bar").lower()
    y_fields = [y for y in y_fields if y]

    if not rows or not y_fields:
        return {**_base(title), "series": []}

    if chart_type == "kpi":
        # Reduce every measure to a total; a custom calculation (ref/literal
        # formula over those totals) wins over the default first-measure sum.
        totals = {y: sum((r.get(y) or 0) for r in rows) for y in y_fields}
        value: Any = totals.get(y_fields[0])
        metric = y_fields[0]
        expression = (kpi or {}).get("expression") or {}
        root = expression.get("root")
        if root:
            try:
                value = evaluate_formula(root, totals)
            except FormulaError as e:
                logger.warning("KPI formula failed — falling back to first measure", error=str(e))
        if (kpi or {}).get("label"):
            metric = kpi["label"]
        return {"type": "kpi", "title": title, "metric": metric, "value": value}

    if chart_type == "table":
        cols = ([x_field] if x_field else []) + y_fields
        return {
            "type": "table",
            "title": title,
            "columns": cols,
            "rows": [[r.get(c) for c in cols] for r in rows],
        }

    x_vals = [str(r.get(x_field, "")) for r in rows] if x_field else list(range(len(rows)))
    option = _base(title)

    if chart_type in ("bar", "line", "area"):
        option["xAxis"] = {"type": "category", "data": x_vals, "axisLabel": _AXIS_LABEL}
        option["yAxis"] = {"type": "value", "axisLabel": _AXIS_LABEL}

        if color_field and len(y_fields) == 1:
            y = y_fields[0]
            groups: dict[str, dict[str, Any]] = {}
            categories: list[str] = []
            for r in rows:
                cat = str(r.get(x_field, ""))
                if cat not in categories:
                    categories.append(cat)
                grp = str(r.get(color_field, ""))
                groups.setdefault(grp, {})[cat] = r.get(y, 0)
            option["xAxis"]["data"] = categories
            option["series"] = [
                _series(chart_type, grp, [vals.get(c, 0) for c in categories])
                for grp, vals in groups.items()
            ]
        else:
            option["series"] = [
                _series(chart_type, y, [r.get(y, 0) for r in rows]) for y in y_fields
            ]

    elif chart_type == "pie":
        y = y_fields[0]
        option.pop("xAxis", None)
        option.pop("yAxis", None)
        option["tooltip"] = {"trigger": "item"}
        option["series"] = [{
            "type": "pie",
            "radius": ["40%", "70%"],
            "data": [{"name": str(r.get(x_field, "")), "value": r.get(y, 0)} for r in rows],
            "label": {"color": "#94a3b8"},
        }]

    elif chart_type == "scatter":
        x_measure = y_fields[0]
        y_measure = y_fields[1] if len(y_fields) > 1 else y_fields[0]
        option["xAxis"] = {"type": "value", "name": x_measure, "axisLabel": _AXIS_LABEL}
        option["yAxis"] = {"type": "value", "name": y_measure, "axisLabel": _AXIS_LABEL}
        option["tooltip"] = {"trigger": "item"}
        option["series"] = [{
            "type": "scatter",
            "data": [[r.get(x_measure), r.get(y_measure)] for r in rows],
            "itemStyle": {"color": ACCENT},
        }]

    elif chart_type == "candlestick":
        # Rows come from the OHLC query: fixed open/high/low/close keys.
        # ECharts candlestick data item order is [open, close, lowest, highest].
        option["xAxis"] = {"type": "category", "data": x_vals, "axisLabel": _AXIS_LABEL}
        option["yAxis"] = {"type": "value", "scale": True, "axisLabel": _AXIS_LABEL}
        option["tooltip"] = {"trigger": "axis", "axisPointer": {"type": "cross"}}
        option["series"] = [{
            "type": "candlestick",
            "name": y_fields[0],
            "data": [
                [r.get("open"), r.get("close"), r.get("low"), r.get("high")] for r in rows
            ],
            "itemStyle": {
                "color": "#22c55e", "color0": "#ef4444",
                "borderColor": "#22c55e", "borderColor0": "#ef4444",
            },
        }]

    else:  # unknown → bar fallback (kept for legacy configs, but surfaced in logs)
        logger.warning("Unknown chart type — rendering as bar", chart_type=chart_type)
        option["xAxis"] = {"type": "category", "data": x_vals, "axisLabel": _AXIS_LABEL}
        option["yAxis"] = {"type": "value", "axisLabel": _AXIS_LABEL}
        option["series"] = [_series("bar", y, [r.get(y, 0) for r in rows]) for y in y_fields]

    return option


def _series(chart_type: str, name: str, data: list) -> dict[str, Any]:
    is_line = chart_type in ("line", "area")
    series: dict[str, Any] = {
        "type": "line" if is_line else "bar",
        "name": name,
        "data": data,
    }
    if chart_type == "area":
        series["areaStyle"] = {"opacity": 0.25}
        series["smooth"] = True
    elif chart_type == "line":
        series["smooth"] = True
    return series


def build_from_definition(rows: list[dict], definition: dict) -> dict[str, Any]:
    """
    Build a chart from a v2 insight definition + rows.
    Uses dimensions[0]/time_dimension for X, measures for Y, dimensions[1] for color.
    """
    dims = definition.get("dimensions") or []
    time_dim = definition.get("time_dimension")
    measures = definition.get("measures") or []
    viz = definition.get("visualization")
    if not viz:
        logger.warning("Definition has no visualization — defaulting to bar")
        viz = "bar"

    x_field = time_dim or (dims[0] if dims else None)
    color_field = None
    if not time_dim and len(dims) > 1:
        color_field = dims[1]
    elif time_dim and dims:
        color_field = dims[0]

    return build_echart_option(
        rows, viz, x_field, measures,
        title=definition.get("title", ""), color_field=color_field,
        kpi=definition.get("kpi"),
    )
