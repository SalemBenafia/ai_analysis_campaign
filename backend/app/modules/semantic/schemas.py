"""
app/modules/semantic/schemas.py
=================================
Semantic query shapes. A SemanticQuery maps ~1:1 to a Cube REST query and is
the single query format used by the builder, saved insights, dashboard
widgets and the copilot's semantic tool.
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

FilterOperator = Literal[
    "equals", "notEquals", "gt", "gte", "lt", "lte", "contains", "set", "notSet",
]

Granularity = Literal["day", "week", "month"]


class SemanticFilter(BaseModel):
    member: str
    operator: FilterOperator = "equals"
    values: list[Union[str, int, float, bool]] = Field(default_factory=list)


class SemanticQuery(BaseModel):
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: Granularity | None = None
    date_range: Union[str, list[str], None] = None
    filters: list[SemanticFilter] = Field(default_factory=list)
    order: dict[str, Literal["asc", "desc"]] = Field(default_factory=dict)
    limit: int = 500
    # "ohlc" turns the query into an open/high/low/close aggregation for
    # candlestick charts (exactly one raw measure + time dimension + granularity).
    mode: Literal["auto", "ohlc"] = "auto"


def migrate_v1_definition(definition: dict) -> dict:
    """
    Upgrade a legacy insight_definition
    {metric, dimension, filters[{field,operator,value}], visualization, date_range}
    to the v2 shape used by SemanticQuery-based execution.
    Legacy metric/dimension names were raw column names — the caller resolves
    them against the member catalog (falls back to `<name>_sum` for metrics).
    """
    if definition.get("version") == 2:
        return definition

    op_map = {"=": "equals", "!=": "notEquals", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
    filters = []
    for f in definition.get("filters") or []:
        filters.append({
            "member": f.get("field") or f.get("member") or "",
            "operator": op_map.get(str(f.get("operator", "=")), str(f.get("operator", "equals"))),
            "values": [f["value"]] if "value" in f else (f.get("values") or []),
        })

    viz = str(definition.get("visualization") or "bar").lower().replace("chart", "").strip()
    return {
        "version": 2,
        "measures": [definition["metric"]] if definition.get("metric") else [],
        "dimensions": [definition["dimension"]] if definition.get("dimension") else [],
        "time_dimension": None,
        "granularity": None,
        "date_range": definition.get("date_range"),
        "filters": filters,
        "order": {},
        "limit": 50,
        "visualization": viz or "bar",
    }
