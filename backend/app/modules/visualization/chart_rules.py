"""
app/modules/visualization/chart_rules.py
==========================================
Per-chart-type shape rules: how many aggregated/raw measures and dimensions
each visualization accepts, and whether a time dimension is required.
Enforced on insight/widget save and by the AI paths; the builder mirrors the
same matrix client-side for instant feedback.

KEEP IN SYNC with frontend/lib/charts/chart-rules.ts
"""
from __future__ import annotations

from typing import Any

# (min, max) — max None means unbounded. "time": allowed | required | forbidden.
# "min_measures": at least N measures of any kind; "no_mix": can't combine raw
# and aggregated measures in the same chart.
CHART_RULES: dict[str, dict[str, Any]] = {
    "bar": {"agg": (1, None), "raw": (0, 0), "dims": (0, 2), "time": "allowed"},
    # Line accepts raw measures for real-time raw tracking (one raw value per
    # row over time), or aggregated measures — but not both mixed.
    "line": {"agg": (0, None), "raw": (0, None), "dims": (0, 2), "time": "allowed",
             "min_measures": 1, "no_mix": True},
    "area": {"agg": (1, None), "raw": (0, 0), "dims": (0, 2), "time": "allowed"},
    "pie": {"agg": (1, 1), "raw": (0, 0), "dims": (1, 1), "time": "forbidden"},
    "scatter": {"agg": (2, 2), "raw": (0, 0), "dims": (0, 1), "time": "forbidden"},
    "kpi": {"agg": (1, None), "raw": (0, 0), "dims": (0, 0), "time": "forbidden"},
    "candlestick": {
        "agg": (0, 0), "raw": (1, 1), "dims": (0, 0),
        "time": "required", "granularity": "required",
    },
    # "table" is intentionally absent: renderer-only legacy type, any shape.
}

# Human-readable requirement per type (switcher tooltips, AI prompts).
RULE_HINTS: dict[str, str] = {
    "bar": "1+ aggregated measures, up to 2 dimensions, optional time on X",
    "line": "1+ measures (raw allowed for real-time tracking), X is a time or category dimension",
    "area": "1+ aggregated measures, X is a time or category dimension",
    "pie": "exactly 1 aggregated measure and exactly 1 dimension, no time",
    "scatter": "exactly 2 aggregated measures (X and Y), optional color dimension",
    "kpi": "1+ aggregated measures, no dimensions",
    "candlestick": "exactly 1 raw measure (e.g. 'spend', not 'spend_sum'), a time dimension and a granularity",
}


def definition_shape(definition: dict, catalog: Any) -> dict[str, Any]:
    """Reduce a v2 insight definition to the shape the rules check."""
    agg = 0
    raw = 0
    for name in definition.get("measures") or []:
        member = catalog.measures.get(name)
        if member is not None and member.row_level:
            raw += 1
        else:
            agg += 1
    return {
        "agg": agg,
        "raw": raw,
        "dims": len(definition.get("dimensions") or []),
        "has_time": bool(definition.get("time_dimension")),
        "has_granularity": bool(definition.get("granularity")),
    }


def _check_range(count: int, bounds: tuple[int, int | None], label: str, chart: str) -> str | None:
    lo, hi = bounds
    if count < lo:
        need = f"at least {lo}" if hi is None or hi > lo else f"exactly {lo}"
        return f"{chart} needs {need} {label} — add {lo - count} more"
    if hi is not None and count > hi:
        allowed = f"at most {hi}" if hi > 0 else "no"
        return f"{chart} allows {allowed} {label} — remove {count - hi}"
    return None


def validate_shape(viz: str, shape: dict[str, Any]) -> list[str]:
    """Return actionable violation messages ([] when the shape fits)."""
    rules = CHART_RULES.get(viz)
    if rules is None:  # table / unknown: renderer-only, never rejected
        return []
    chart = viz.capitalize()
    messages: list[str] = []

    msg = _check_range(shape["agg"], rules["agg"], "aggregated measure(s)", chart)
    if msg:
        messages.append(msg)
    msg = _check_range(shape["raw"], rules["raw"], "raw measure(s)", chart)
    if msg:
        if viz == "candlestick" and shape["raw"] < 1:
            msg = "Candlestick needs exactly 1 raw measure (e.g. 'spend', not 'spend_sum')"
        messages.append(msg)
    msg = _check_range(shape["dims"], rules["dims"], "dimension(s)", chart)
    if msg:
        messages.append(msg)

    min_measures = rules.get("min_measures")
    if min_measures and shape["agg"] + shape["raw"] < min_measures:
        messages.append(f"{chart} needs at least {min_measures} measure — add one")
    if rules.get("no_mix") and shape["agg"] > 0 and shape["raw"] > 0:
        messages.append(f"{chart} can't mix raw and aggregated measures — use one kind")

    time_rule = rules.get("time", "allowed")
    if time_rule == "required" and not shape["has_time"]:
        messages.append(f"{chart} needs a time dimension on X")
    elif time_rule == "forbidden" and shape["has_time"]:
        messages.append(f"{chart} can't use a time dimension — remove it from X")

    if rules.get("granularity") == "required" and shape["has_time"] and not shape["has_granularity"]:
        messages.append(f"{chart} needs a granularity (day, week or month)")

    return messages


def validate_definition(definition: dict, catalog: Any) -> list[str]:
    """Validate a v2 insight definition against its visualization's rules."""
    viz = str(definition.get("visualization") or "bar").lower()
    return validate_shape(viz, definition_shape(definition, catalog))
