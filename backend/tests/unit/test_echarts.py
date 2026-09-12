"""Shared ECharts option builder."""
from __future__ import annotations

import pytest

from app.modules.visualization.echarts import build_echart_option, build_from_definition

ROWS = [
    {"campaign": "A", "roas": 4.8, "spend_sum": 500},
    {"campaign": "B", "roas": 3.2, "spend_sum": 800},
    {"campaign": "C", "roas": 1.9, "spend_sum": 300},
]


class TestBuildOption:
    def test_bar_single_measure(self):
        opt = build_echart_option(ROWS, "bar", "campaign", ["roas"], title="ROAS")
        assert opt["xAxis"]["data"] == ["A", "B", "C"]
        assert opt["series"][0]["type"] == "bar"
        assert opt["series"][0]["data"] == [4.8, 3.2, 1.9]

    def test_multi_measure_series(self):
        opt = build_echart_option(ROWS, "line", "campaign", ["roas", "spend_sum"])
        assert len(opt["series"]) == 2
        assert {s["name"] for s in opt["series"]} == {"roas", "spend_sum"}

    def test_pie(self):
        opt = build_echart_option(ROWS, "pie", "campaign", ["spend_sum"])
        assert opt["series"][0]["type"] == "pie"
        assert "xAxis" not in opt

    def test_kpi(self):
        opt = build_echart_option(ROWS, "kpi", None, ["spend_sum"])
        assert opt["type"] == "kpi"
        assert opt["value"] == 1600

    def test_table(self):
        opt = build_echart_option(ROWS, "table", "campaign", ["roas"])
        assert opt["columns"] == ["campaign", "roas"]
        assert opt["rows"][0] == ["A", 4.8]

    def test_empty_rows_safe(self):
        opt = build_echart_option([], "bar", "campaign", ["roas"])
        assert opt["series"] == []


OHLC_ROWS = [
    {"date": "2025-01-01", "open": 10, "high": 30, "low": 10, "close": 20},
    {"date": "2025-01-02", "open": 25, "high": 25, "low": 5, "close": 5},
]


class TestCandlestick:
    def test_series_shape(self):
        opt = build_echart_option(OHLC_ROWS, "candlestick", "date", ["spend"])
        assert opt["series"][0]["type"] == "candlestick"
        # ECharts data item order is [open, close, lowest, highest].
        assert opt["series"][0]["data"][0] == [10, 20, 10, 30]
        assert opt["xAxis"]["data"] == ["2025-01-01", "2025-01-02"]
        assert opt["yAxis"]["scale"] is True


class TestKpiExpression:
    def test_custom_calculation_over_totals(self):
        rows = [
            {"revenue_sum": 400, "spend_sum": 100},
            {"revenue_sum": 600, "spend_sum": 150},
        ]
        kpi = {
            "label": "ROI",
            "expression": {"type": "formula", "root": {
                "type": "binary", "op": "/",
                "left": {
                    "type": "binary", "op": "-",
                    "left": {"type": "ref", "measure": "revenue_sum"},
                    "right": {"type": "ref", "measure": "spend_sum"},
                },
                "right": {"type": "ref", "measure": "spend_sum"},
            }},
        }
        opt = build_echart_option(rows, "kpi", None, ["revenue_sum", "spend_sum"], kpi=kpi)
        assert opt["type"] == "kpi"
        assert opt["metric"] == "ROI"
        assert opt["value"] == pytest.approx((1000 - 250) / 250)

    def test_without_expression_keeps_first_measure_total(self):
        opt = build_echart_option([{"a": 1}, {"a": 2}], "kpi", None, ["a"])
        assert opt["value"] == 3

    def test_definition_passes_kpi_through(self):
        definition = {
            "measures": ["a"], "visualization": "kpi",
            "kpi": {"expression": {"type": "formula", "root": {
                "type": "binary", "op": "*",
                "left": {"type": "ref", "measure": "a"},
                "right": {"type": "literal", "value": 2},
            }}},
        }
        opt = build_from_definition([{"a": 4}], definition)
        assert opt["value"] == 8


class TestBuildFromDefinition:
    def test_uses_dimensions_and_measures(self):
        definition = {
            "dimensions": ["campaign"], "measures": ["roas"], "visualization": "bar",
        }
        opt = build_from_definition(ROWS, definition)
        assert opt["series"][0]["data"] == [4.8, 3.2, 1.9]

    def test_time_dimension_is_x(self):
        rows = [{"date": "2025-01-01", "spend_sum": 5}, {"date": "2025-01-02", "spend_sum": 7}]
        definition = {
            "time_dimension": "date", "measures": ["spend_sum"], "visualization": "line",
        }
        opt = build_from_definition(rows, definition)
        assert opt["xAxis"]["data"] == ["2025-01-01", "2025-01-02"]
