"""NL-create parsing/validation and definition→query mapping (raw + OHLC)."""
from __future__ import annotations

import uuid

import pytest

from app.db.models import ColumnType, Dataset, DatasetColumn
from app.modules.insights.service import _parse_nl_definition, definition_to_query
from app.modules.semantic.registry import build_catalog

DS_ID = uuid.uuid4()


def _col(name, col_type, *, metric=False, dim=False):
    return DatasetColumn(
        id=uuid.uuid4(), dataset_id=DS_ID, name=name, display_name=name.title(),
        semantic_name=name, col_type=col_type, position=0,
        is_metric=metric, is_dimension=dim,
    )


@pytest.fixture()
def catalog():
    ds = Dataset(
        id=DS_ID, owner_id=uuid.uuid4(), name="t", file_name="t.csv",
        file_format="csv", duckdb_table="t",
    )
    return build_catalog(ds, [
        _col("campaign", ColumnType.TEXT, dim=True),
        _col("date", ColumnType.DATE, dim=True),
        _col("spend", ColumnType.FLOAT, metric=True),
        _col("revenue", ColumnType.FLOAT, metric=True),
    ], [])


class TestParseNLDefinition:
    def test_valid_line_definition(self, catalog):
        text = (
            '{"measures": ["spend_sum"], "dimensions": [], "time_dimension": "date", '
            '"granularity": "day", "visualization": "line"}'
        )
        definition, errors = _parse_nl_definition(text, catalog)
        assert errors == []
        assert definition["visualization"] == "line"

    def test_json_inside_fences_parsed(self, catalog):
        text = '```json\n{"measures": ["spend_sum"], "visualization": "kpi"}\n```'
        definition, errors = _parse_nl_definition(text, catalog)
        assert errors == []
        assert definition["visualization"] == "kpi"

    def test_invalid_visualization_rejected(self, catalog):
        _, errors = _parse_nl_definition(
            '{"measures": ["spend_sum"], "visualization": "hologram"}', catalog
        )
        assert errors

    def test_rule_violation_reported(self, catalog):
        _, errors = _parse_nl_definition(
            '{"measures": ["spend_sum", "revenue_sum"], "dimensions": ["campaign"], '
            '"visualization": "pie"}',
            catalog,
        )
        assert any("Pie" in e for e in errors)

    def test_unknown_member_reported(self, catalog):
        _, errors = _parse_nl_definition(
            '{"measures": ["banana_sum"], "dimensions": ["campaign"], "visualization": "bar"}',
            catalog,
        )
        assert any("unknown members" in e for e in errors)

    def test_not_json_reported(self, catalog):
        _, errors = _parse_nl_definition("sorry, I cannot help", catalog)
        assert errors

    def test_candlestick_definition_maps_to_ohlc_query(self, catalog):
        text = (
            '{"measures": ["spend"], "time_dimension": "date", "granularity": "day", '
            '"visualization": "candlestick"}'
        )
        definition, errors = _parse_nl_definition(text, catalog)
        assert errors == []
        query = definition_to_query({**definition, "version": 2}, catalog)
        assert query.mode == "ohlc"
        assert query.measures == ["spend"]


class TestDefinitionToQuery:
    def test_legacy_v1_metric_resolves_to_sum_not_raw(self, catalog):
        query = definition_to_query({"metric": "spend", "dimension": "campaign"}, catalog)
        assert query.measures == ["spend_sum"]

    def test_v2_raw_measure_kept(self, catalog):
        query = definition_to_query({"version": 2, "measures": ["spend"]}, catalog)
        assert query.measures == ["spend"]
        assert query.mode == "auto"
