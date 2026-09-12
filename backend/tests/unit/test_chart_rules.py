"""Per-chart-type shape rules (mirrored by frontend/lib/charts/chart-rules.ts)."""
from __future__ import annotations

import uuid

import pytest

from app.db.models import ColumnType, Dataset, DatasetColumn
from app.modules.semantic.registry import build_catalog
from app.modules.visualization.chart_rules import validate_definition, validate_shape

DS_ID = uuid.uuid4()


def shape(agg=0, raw=0, dims=0, time=False, gran=False):
    return {"agg": agg, "raw": raw, "dims": dims, "has_time": time, "has_granularity": gran}


class TestValidateShape:
    def test_bar_ok(self):
        assert validate_shape("bar", shape(agg=1, dims=1)) == []

    def test_bar_needs_measure(self):
        assert validate_shape("bar", shape()) != []

    def test_bar_rejects_raw(self):
        assert any("raw" in m for m in validate_shape("bar", shape(agg=1, raw=1, dims=1)))

    def test_line_allows_raw_for_realtime(self):
        assert validate_shape("line", shape(raw=1, time=True, gran=True)) == []
        assert validate_shape("line", shape(raw=1)) == []

    def test_line_allows_aggregated(self):
        assert validate_shape("line", shape(agg=2, dims=1)) == []

    def test_line_needs_at_least_one_measure(self):
        assert any("at least" in m for m in validate_shape("line", shape(dims=1)))

    def test_line_cannot_mix_raw_and_aggregated(self):
        assert any("mix" in m for m in validate_shape("line", shape(agg=1, raw=1)))

    def test_pie_exactly_one_measure_and_dim(self):
        assert validate_shape("pie", shape(agg=1, dims=1)) == []
        assert validate_shape("pie", shape(agg=2, dims=1)) != []
        assert validate_shape("pie", shape(agg=1, dims=0)) != []
        assert validate_shape("pie", shape(agg=1, dims=1, time=True)) != []

    def test_scatter_two_measures(self):
        assert validate_shape("scatter", shape(agg=2)) == []
        assert validate_shape("scatter", shape(agg=1)) != []

    def test_kpi_no_dims(self):
        assert validate_shape("kpi", shape(agg=1)) == []
        assert validate_shape("kpi", shape(agg=1, dims=1)) != []

    def test_candlestick(self):
        assert validate_shape("candlestick", shape(raw=1, time=True, gran=True)) == []
        assert any(
            "raw" in m.lower()
            for m in validate_shape("candlestick", shape(agg=1, time=True, gran=True))
        )
        assert any("time" in m for m in validate_shape("candlestick", shape(raw=1)))
        assert any(
            "granularity" in m
            for m in validate_shape("candlestick", shape(raw=1, time=True))
        )

    def test_table_and_unknown_never_rejected(self):
        assert validate_shape("table", shape(agg=5, raw=3, dims=4)) == []
        assert validate_shape("heatmap", shape()) == []


class TestValidateDefinition:
    @pytest.fixture()
    def catalog(self):
        def col(name, col_type, *, metric=False, dim=False):
            return DatasetColumn(
                id=uuid.uuid4(), dataset_id=DS_ID, name=name, display_name=name.title(),
                semantic_name=name, col_type=col_type, position=0,
                is_metric=metric, is_dimension=dim,
            )

        ds = Dataset(
            id=DS_ID, owner_id=uuid.uuid4(), name="t", file_name="t.csv",
            file_format="csv", duckdb_table="t",
        )
        return build_catalog(ds, [
            col("campaign", ColumnType.TEXT, dim=True),
            col("date", ColumnType.DATE, dim=True),
            col("spend", ColumnType.FLOAT, metric=True),
        ], [])

    def test_candlestick_wants_raw(self, catalog):
        definition = {
            "measures": ["spend"], "dimensions": [],
            "time_dimension": "date", "granularity": "day",
            "visualization": "candlestick",
        }
        assert validate_definition(definition, catalog) == []
        assert validate_definition({**definition, "measures": ["spend_sum"]}, catalog) != []

    def test_bar_wants_aggregated(self, catalog):
        definition = {"measures": ["spend_sum"], "dimensions": ["campaign"], "visualization": "bar"}
        assert validate_definition(definition, catalog) == []
        assert validate_definition({**definition, "measures": ["spend"]}, catalog) != []
