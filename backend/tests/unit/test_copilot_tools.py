"""Copilot tools: dataset locking, chart_tool one-call charts, token caps."""
from __future__ import annotations

import json

import pytest

import app.modules.copilot.tools as tools_mod
import app.modules.datasets.service as ds_service
from app.modules.copilot.tools import CopilotContext, make_tools
from app.modules.semantic.schemas import SemanticQuery
from tests.conftest import TABLE

MEMBERS = {
    "dimensions": [
        {"name": "campaign", "kind": "dimension", "type": "string", "agg": None, "row_level": False},
        {"name": "date", "kind": "dimension", "type": "time", "agg": None, "row_level": False},
    ],
    "measures": [
        {"name": "spend", "kind": "measure", "agg": None, "row_level": True},
        {"name": "spend_sum", "kind": "measure", "agg": "SUM", "row_level": False},
        {"name": "revenue_sum", "kind": "measure", "agg": "SUM", "row_level": False},
        {"name": "roas", "kind": "computed", "agg": None, "row_level": False},
    ],
}


@pytest.fixture()
def ctx():
    return CopilotContext(
        dataset_id="00000000-0000-0000-0000-000000000000",
        dataset_table=TABLE,
        allowed_columns={"campaign", "spend", "revenue"},
        cube_name="ds_test",
        members=MEMBERS,
        user_id="00000000-0000-0000-0000-000000000000",
    )


@pytest.fixture(autouse=True)
def _patch_duckdb(monkeypatch, duck):
    monkeypatch.setattr(ds_service, "get_duckdb", lambda: duck)


@pytest.fixture()
def fake_query(monkeypatch):
    """Offline stand-in for the semantic layer — records the queries it gets."""
    captured: list[SemanticQuery] = []

    async def fake_exec(ctx, query):
        captured.append(query)
        if query.mode == "ohlc":
            rows = [{"date": "2025-01-01", "open": 1.0, "high": 3.0, "low": 0.5, "close": 2.0}]
        else:
            rows = [
                {"campaign": "A", "spend_sum": 100},
                {"campaign": "B", "spend_sum": 200},
            ]
        return {"rows": rows, "meta": {"engine": "duckdb", "took_ms": 1}}

    monkeypatch.setattr(tools_mod, "_execute_semantic_query", fake_exec)
    return captured


def _get_tool(tools, name):
    return next(t for t in tools if t.name == name)


class TestSqlToolLocking:
    def test_valid_select_runs(self, ctx):
        sql_tool = _get_tool(make_tools(ctx), "sql_tool")
        out = json.loads(sql_tool.invoke({"sql": f"SELECT campaign FROM {TABLE} LIMIT 1"}))
        assert "rows" in out

    def test_other_table_rejected(self, ctx):
        sql_tool = _get_tool(make_tools(ctx), "sql_tool")
        out = json.loads(sql_tool.invoke({"sql": "SELECT * FROM users"}))
        assert "error" in out

    def test_multi_statement_rejected(self, ctx):
        sql_tool = _get_tool(make_tools(ctx), "sql_tool")
        out = json.loads(sql_tool.invoke({"sql": f"SELECT 1 FROM {TABLE}; DROP TABLE {TABLE}"}))
        assert "error" in out


class TestChartTool:
    async def test_one_call_builds_and_stashes_chart(self, ctx, fake_query):
        chart = _get_tool(make_tools(ctx), "chart_tool")
        out = json.loads(await chart.ainvoke({
            "chart_type": "bar", "measures": ["spend_sum"], "dimension": "campaign",
        }))
        assert out["chart_created"] == "bar"
        assert out["rows"] == 2
        # The full ECharts config never round-trips through the model…
        assert "series" not in json.dumps(out)
        # …it lands on the ctx for the router/extract step.
        assert ctx.last_echart_config["series"][0]["type"] == "bar"
        assert ctx.last_echart_config["series"][0]["data"] == [100, 200]
        assert ctx.last_semantic_query["measures"] == ["spend_sum"]

    async def test_rule_violation_returned_as_error(self, ctx, fake_query):
        chart = _get_tool(make_tools(ctx), "chart_tool")
        out = json.loads(await chart.ainvoke({
            "chart_type": "pie", "measures": ["spend_sum", "revenue_sum"], "dimension": "campaign",
        }))
        assert "error" in out and "Pie" in out["error"]
        assert fake_query == []  # rejected before any query ran
        assert ctx.last_echart_config is None

    async def test_candlestick_switches_to_ohlc_mode(self, ctx, fake_query):
        chart = _get_tool(make_tools(ctx), "chart_tool")
        out = json.loads(await chart.ainvoke({
            "chart_type": "candlestick", "measures": ["spend"],
            "time_dimension": "date", "granularity": "day",
        }))
        assert out["chart_created"] == "candlestick"
        assert fake_query[0].mode == "ohlc"
        assert ctx.last_echart_config["series"][0]["type"] == "candlestick"
        assert ctx.last_echart_config["series"][0]["data"][0] == [1.0, 2.0, 0.5, 3.0]

    async def test_chart_type_enum_in_schema(self, ctx):
        chart = _get_tool(make_tools(ctx), "chart_tool")
        schema = chart.args_schema.model_json_schema()
        assert set(schema["properties"]["chart_type"]["enum"]) == {
            "bar", "line", "area", "pie", "scatter", "kpi", "candlestick", "table",
        }


class TestSemanticQueryTool:
    async def test_rows_capped_for_token_economy(self, ctx, monkeypatch):
        async def many_rows(ctx_, query):
            return {"rows": [{"n": i} for i in range(500)], "meta": {}}
        monkeypatch.setattr(tools_mod, "_execute_semantic_query", many_rows)

        sq = _get_tool(make_tools(ctx), "semantic_query_tool")
        out = json.loads(await sq.ainvoke({"measures": ["spend_sum"]}))
        assert len(out["rows"]) == tools_mod._TOOL_ROW_CAP
        assert out["total_rows"] == 500
        assert out["truncated"] is True


class TestVisualizationTool:
    def test_builds_from_rows_and_stashes(self, ctx):
        viz = _get_tool(make_tools(ctx), "visualization_tool")
        rows = json.dumps([{"campaign": "A", "spend": 100}, {"campaign": "B", "spend": 200}])
        out = json.loads(viz.invoke({
            "chart_type": "bar", "data": rows, "x_field": "campaign", "y_fields": ["spend"],
        }))
        assert out == {"chart_created": "bar", "points": 2}
        assert ctx.last_echart_config["series"][0]["data"] == [100, 200]

    def test_chart_type_is_a_real_enum_in_the_tool_schema(self, ctx):
        viz = _get_tool(make_tools(ctx), "visualization_tool")
        schema = viz.args_schema.model_json_schema()
        assert set(schema["properties"]["chart_type"]["enum"]) == {
            "bar", "line", "area", "pie", "scatter", "kpi", "candlestick",
        }
        assert schema["properties"]["y_fields"]["type"] == "array"

    def test_scatter_requires_two_measures(self, ctx):
        viz = _get_tool(make_tools(ctx), "visualization_tool")
        out = json.loads(viz.invoke({
            "chart_type": "scatter", "data": json.dumps([{"a": 1}]), "y_fields": ["a"],
        }))
        assert "error" in out

    def test_candlestick_requires_ohlc_rows(self, ctx):
        viz = _get_tool(make_tools(ctx), "visualization_tool")
        rows = json.dumps([{"date": "2025-01-01", "spend": 1}])
        out = json.loads(viz.invoke({
            "chart_type": "candlestick", "data": rows, "x_field": "date", "y_fields": ["spend"],
        }))
        assert "error" in out and "chart_tool" in out["error"]


def test_tool_names(ctx):
    names = {t.name for t in make_tools(ctx)}
    assert names == {
        "chart_tool", "semantic_query_tool", "sql_tool", "insight_tool", "visualization_tool",
    }
