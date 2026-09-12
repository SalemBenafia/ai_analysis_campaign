"""
app/modules/copilot/tools.py
==============================
LangChain tools for the copilot agent, built per-conversation via
make_tools(ctx). Tools are locked to the conversation's dataset:
  - chart_tool          → PREFERRED for charts: query + chart in ONE call
  - semantic_query_tool → validated semantic query (numbers without a chart)
  - sql_tool            → sqlglot-validated SELECT, only the dataset's table
  - insight_tool        → automated discovery
  - visualization_tool  → chart from rows already in hand (rare)

Token economy: chart configs are NEVER echoed back to the model — they are
stashed on the mutable ctx (ctx.last_echart_config) and the tool returns a
tiny ack + small sample. Query results returned to the model are row-capped.
The semantic tool records the last validated query into the same holder so
the router can offer "save as insight" / "add to dashboard".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.tools import tool

from app.modules.analytics.sql_builder import UnsafeSQLError, validate_select
from app.modules.datasets.service import run_query
from app.modules.semantic.schemas import SemanticQuery
from app.modules.visualization.chart_rules import validate_shape
from app.modules.visualization.echarts import build_echart_option

# Rows the MODEL sees from a query (full rows never need to round-trip:
# chart_tool builds charts server-side).
_TOOL_ROW_CAP = 40
_SAMPLE_ROWS = 3
_JSON_COMPACT = {"separators": (",", ":"), "default": str}


@dataclass
class CopilotContext:
    dataset_id: str
    dataset_table: str
    allowed_columns: set[str]
    cube_name: str
    members: dict[str, Any]                 # {"dimensions": [...], "measures": [...]}
    user_id: str
    last_semantic_query: dict | None = field(default=None)   # mutated by tools
    last_echart_config: dict | None = field(default=None)    # mutated by chart tools


async def _execute_semantic_query(ctx: CopilotContext, query: SemanticQuery) -> dict:
    """Run a semantic query as the conversation's user (patchable in tests)."""
    from sqlalchemy import select as sa_select

    from app.db.models import User
    from app.db.session import AsyncSessionLocal
    from app.modules.semantic.service import run_semantic_query

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(sa_select(User).where(User.id == ctx.user_id))
        ).scalar_one()
        return await run_semantic_query(db, user, ctx.dataset_id, query)


def _chart_shape(
    ctx: CopilotContext,
    measures: list[str],
    dimension: str | None,
    time_dimension: str | None,
    granularity: str | None,
) -> dict:
    """Reduce chart args to the shape the chart rules validate."""
    by_name = {m["name"]: m for m in ctx.members.get("measures", [])}
    raw = sum(1 for m in measures if by_name.get(m, {}).get("row_level"))
    return {
        "agg": len(measures) - raw,
        "raw": raw,
        "dims": 1 if dimension else 0,
        "has_time": bool(time_dimension),
        "has_granularity": bool(granularity),
    }


def make_tools(ctx: CopilotContext) -> list:
    @tool
    async def chart_tool(
        chart_type: Literal["bar", "line", "area", "pie", "scatter", "kpi", "candlestick", "table"],
        measures: list[str],
        dimension: str | None = None,
        time_dimension: str | None = None,
        granularity: Literal["day", "week", "month"] | None = None,
        date_range: str | None = None,
        title: str = "",
        limit: int = 100,
    ) -> str:
        """
        PREFERRED for ANY chart/graph/plot request: runs the semantic query AND
        builds the chart in one call. The chart attaches to your answer
        automatically — you only summarize the numbers.
        measures: member names (aggregated like spend_sum/roas for most charts;
        a raw name like spend ONLY for candlestick or a raw line).
        dimension: category/breakdown member. candlestick: exactly one raw
        measure + time_dimension + granularity.
        Returns the row count and a small sample.
        """
        problems = validate_shape(
            chart_type, _chart_shape(ctx, measures, dimension, time_dimension, granularity)
        )
        if problems:
            return json.dumps({"error": "; ".join(problems)}, **_JSON_COMPACT)

        query = SemanticQuery(
            measures=measures,
            dimensions=[dimension] if dimension else [],
            time_dimension=time_dimension,
            granularity=granularity,
            date_range=date_range,
            limit=limit,
            mode="ohlc" if chart_type == "candlestick" else "auto",
        )
        try:
            result = await _execute_semantic_query(ctx, query)
        except Exception as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)

        rows = result["rows"]
        x_field = time_dimension or dimension
        color_field = dimension if (time_dimension and dimension) else None
        option = build_echart_option(
            rows, chart_type, x_field, measures, title=title, color_field=color_field
        )
        ctx.last_semantic_query = query.model_dump()
        ctx.last_echart_config = option

        ack: dict[str, Any] = {
            "chart_created": chart_type,
            "rows": len(rows),
            "sample": rows[:_SAMPLE_ROWS],
        }
        if not rows:
            ack["note"] = "no data matched — say so and suggest removing filters"
        return json.dumps(ack, **_JSON_COMPACT)

    @tool
    async def semantic_query_tool(
        measures: list[str],
        dimensions: list[str] | None = None,
        time_dimension: str | None = None,
        granularity: str | None = None,
        date_range: str | None = None,
        limit: int = 100,
        mode: Literal["auto", "ohlc"] = "auto",
    ) -> str:
        """
        Aggregation numbers WITHOUT a chart (totals, averages, group-bys).
        Uses defined members (measures like spend_sum, roas; dimensions like
        campaign). For charts call chart_tool instead. Returns JSON rows
        (capped — check "total_rows").
        """
        query = SemanticQuery(
            measures=measures,
            dimensions=dimensions or [],
            time_dimension=time_dimension,
            granularity=granularity,
            date_range=date_range,
            limit=limit,
            mode=mode,
        )
        try:
            result = await _execute_semantic_query(ctx, query)
        except Exception as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)
        ctx.last_semantic_query = query.model_dump()
        rows = result["rows"]
        return json.dumps({
            "rows": rows[:_TOOL_ROW_CAP],
            "total_rows": len(rows),
            "truncated": len(rows) > _TOOL_ROW_CAP,
        }, **_JSON_COMPACT)

    @tool
    def sql_tool(sql: str) -> str:
        """Execute a read-only SELECT against the current dataset (row-level inspection only). Returns JSON rows."""
        try:
            safe = validate_select(sql.strip(), ctx.dataset_table)
        except UnsafeSQLError as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)
        try:
            rows = run_query(safe, max_rows=500)
            return json.dumps({
                "rows": rows[:_TOOL_ROW_CAP],
                "total_rows": len(rows),
                "truncated": len(rows) > _TOOL_ROW_CAP,
            }, **_JSON_COMPACT)
        except Exception as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)

    @tool
    def insight_tool(metric_cols: str, dimension_cols: str) -> str:
        """Run automated discovery (top/bottom performers, anomalies, trends). Pass comma-separated column names."""
        from app.modules.insights.engine import run_full_discovery
        try:
            metrics = [c.strip() for c in metric_cols.split(",") if c.strip()]
            dims = [c.strip() for c in dimension_cols.split(",") if c.strip()]
            findings = run_full_discovery(ctx.dataset_table, metrics, dims, ctx.allowed_columns)
            return json.dumps(findings, **_JSON_COMPACT)
        except Exception as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)

    @tool
    def visualization_tool(
        chart_type: Literal["bar", "line", "area", "pie", "scatter", "kpi", "candlestick"],
        data: str,
        y_fields: list[str],
        x_field: str | None = None,
        title: str = "",
    ) -> str:
        """
        Build a chart from rows you ALREADY have (e.g. sql_tool output).
        Prefer chart_tool — it queries and charts in one call.
        data: JSON string of rows. y_fields: measure keys (2 for scatter;
        ["open","close","low","high"] for candlestick). x_field: category/time key.
        """
        try:
            rows = json.loads(data) if isinstance(data, str) else data
            problems = []
            if chart_type == "pie" and len(y_fields) != 1:
                problems.append("pie needs exactly 1 y_field")
            if chart_type == "scatter" and len(y_fields) != 2:
                problems.append("scatter needs exactly 2 y_fields (the X and Y measures)")
            if chart_type == "candlestick" and rows and not {"open", "high", "low", "close"} <= set(rows[0]):
                problems.append(
                    "candlestick needs rows with open/high/low/close keys — "
                    'use chart_tool with chart_type="candlestick" instead'
                )
            if problems:
                return json.dumps({"error": "; ".join(problems)}, **_JSON_COMPACT)
            option = build_echart_option(rows, chart_type, x_field, y_fields, title=title)
            ctx.last_echart_config = option
            return json.dumps({"chart_created": chart_type, "points": len(rows)}, **_JSON_COMPACT)
        except Exception as e:
            return json.dumps({"error": str(e)}, **_JSON_COMPACT)

    return [chart_tool, semantic_query_tool, sql_tool, insight_tool, visualization_tool]
