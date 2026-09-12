"""Semantic layer: catalog building, query resolution, Cube YAML generation,
metric autodetection and the DuckDB fallback compiler."""
from __future__ import annotations

import uuid

import pytest
import yaml

import app.modules.semantic.duckdb_backend as duckdb_backend
from app.db.models import ColumnType, Dataset, DatasetColumn, SemanticMetric
from app.modules.semantic.cube_models import build_cube_for_dataset, build_models_yaml
from app.modules.semantic.duckdb_backend import compile_ohlc_sql, compile_semantic_sql
from app.modules.semantic.metrics_autodetect import detect_metric_definitions
from app.modules.semantic.registry import (
    UnknownMemberError,
    build_catalog,
    cube_name_for,
    normalize_cube_rows,
    resolve_cube_query,
)
from app.modules.semantic.schemas import SemanticFilter, SemanticQuery, migrate_v1_definition
from tests.conftest import TABLE

DS_ID = uuid.UUID("aabbccdd-0000-0000-0000-000000000000")


def _col(name, sem, col_type, *, metric=False, dim=False, pos=0):
    return DatasetColumn(
        id=uuid.uuid4(), dataset_id=DS_ID, name=name, display_name=name.title(),
        semantic_name=sem, col_type=col_type, position=pos,
        is_metric=metric, is_dimension=dim,
    )


@pytest.fixture()
def dataset():
    return Dataset(
        id=DS_ID, owner_id=uuid.uuid4(), name="test", file_name="t.csv",
        file_format="csv", duckdb_table=TABLE,
        marts_key=f"marts/{DS_ID}/clean.parquet",
    )


@pytest.fixture()
def columns():
    return [
        _col("Campaign Name", "campaign_name", ColumnType.TEXT, dim=True, pos=0),
        _col("country", "country", ColumnType.TEXT, dim=True, pos=1),
        _col("date", "date", ColumnType.DATE, dim=True, pos=2),
        _col("Spend", "spend", ColumnType.FLOAT, metric=True, pos=3),
        _col("Revenue", "revenue", ColumnType.FLOAT, metric=True, pos=4),
        _col("Impressions", "impressions", ColumnType.INTEGER, metric=True, pos=5),
        _col("Clicks", "clicks", ColumnType.INTEGER, metric=True, pos=6),
        _col("Purchases", "purchases", ColumnType.INTEGER, metric=True, pos=7),
    ]


@pytest.fixture()
def roas_metric():
    return SemanticMetric(
        id=uuid.uuid4(), dataset_id=DS_ID, name="roas", display_name="ROAS",
        expression={
            "type": "ratio",
            "numerator": {"agg": "sum", "column": "revenue"},
            "denominator": {"agg": "sum", "column": "spend"},
        },
        is_auto=True,
    )


@pytest.fixture()
def catalog(dataset, columns, roas_metric):
    return build_catalog(dataset, columns, [roas_metric])


class TestCatalog:
    def test_members_present(self, catalog):
        assert "campaign_name" in catalog.dimensions
        assert catalog.dimensions["date"].type == "time"
        assert "spend_sum" in catalog.measures
        assert "row_count" in catalog.measures
        assert catalog.measures["roas"].kind == "computed"

    def test_unknown_member_raises(self, catalog):
        with pytest.raises(UnknownMemberError):
            catalog.get("nonexistent")


class TestResolveCubeQuery:
    def test_full_query(self, dataset, catalog):
        cube = cube_name_for(dataset)
        q = SemanticQuery(
            measures=["roas", "spend_sum"],
            dimensions=["campaign_name"],
            time_dimension="date", granularity="day", date_range="last 30 days",
            filters=[SemanticFilter(member="spend_sum", operator="gt", values=[500])],
            order={"roas": "desc"}, limit=20,
        )
        resolved = resolve_cube_query(q, catalog)
        assert resolved["measures"] == [f"{cube}.roas", f"{cube}.spend_sum"]
        assert resolved["timeDimensions"][0]["dateRange"] == "last 30 days"
        assert resolved["filters"][0]["values"] == ["500"]
        assert resolved["order"] == [[f"{cube}.roas", "desc"]]

    def test_unknown_measure_rejected(self, catalog):
        with pytest.raises(UnknownMemberError):
            resolve_cube_query(SemanticQuery(measures=["evil"]), catalog)

    def test_dimension_as_measure_rejected(self, catalog):
        with pytest.raises(UnknownMemberError):
            resolve_cube_query(SemanticQuery(measures=["campaign_name"]), catalog)

    def test_limit_clamped(self, catalog):
        resolved = resolve_cube_query(SemanticQuery(measures=["row_count"], limit=999999), catalog)
        assert resolved["limit"] == 5000


class TestNormalizeRows:
    def test_prefix_and_granularity_stripped(self, dataset, catalog):
        cube = cube_name_for(dataset)
        rows = [{f"{cube}.date.day": "2025-01-01", f"{cube}.date": "x", f"{cube}.spend_sum": 5}]
        out = normalize_cube_rows(rows, catalog)
        assert out == [{"date": "2025-01-01", "spend_sum": 5}]


class TestCubeYaml:
    def test_cube_model_shape(self, dataset, columns, roas_metric):
        model = build_cube_for_dataset(dataset, columns, [roas_metric])
        assert model["name"] == cube_name_for(dataset)
        assert "read_parquet" in model["sql"]
        measure_names = {m["name"] for m in model["measures"]}
        assert {"row_count", "spend_sum", "spend_avg", "roas"} <= measure_names
        roas = next(m for m in model["measures"] if m["name"] == "roas")
        assert roas["type"] == "number"
        assert 'SUM("revenue")' in roas["sql"] and "NULLIF" in roas["sql"]

    def test_yaml_parses_and_skips_datasets_without_marts(self, dataset, columns, roas_metric):
        no_marts = Dataset(
            id=uuid.uuid4(), owner_id=uuid.uuid4(), name="x", file_name="x.csv",
            file_format="csv", duckdb_table="t", marts_key=None,
        )
        text = build_models_yaml([
            (dataset, columns, [roas_metric]),
            (no_marts, [], []),
        ])
        parsed = yaml.safe_load(text)
        assert len(parsed["cubes"]) == 1


class TestAutodetect:
    def test_marketing_metrics_detected(self, columns):
        names = {d["name"] for d in detect_metric_definitions(columns)}
        assert {"roas", "ctr", "cpa", "cpm", "cpc", "aov", "cvr"} == names

    def test_no_metrics_without_matching_columns(self):
        cols = [_col("Temperature", "temperature", ColumnType.FLOAT, metric=True)]
        assert detect_metric_definitions(cols) == []


class TestMigrateV1:
    def test_legacy_definition_upgraded(self):
        v2 = migrate_v1_definition({
            "metric": "spend", "dimension": "campaign",
            "filters": [{"field": "spend", "operator": ">", "value": 500}],
            "visualization": "BarChart", "date_range": "last_30_days",
        })
        assert v2["version"] == 2
        assert v2["measures"] == ["spend"]
        assert v2["filters"][0]["operator"] == "gt"
        assert v2["visualization"] == "bar"

    def test_v2_definition_untouched(self):
        d = {"version": 2, "measures": ["roas"]}
        assert migrate_v1_definition(d) is d


class TestDuckDBFallback:
    def test_compile_and_execute(self, duck, monkeypatch, dataset, roas_metric):
        # Catalog whose original names == semantic names (conftest table).
        cols = [
            _col("campaign", "campaign", ColumnType.TEXT, dim=True),
            _col("country", "country", ColumnType.TEXT, dim=True),
            _col("date", "date", ColumnType.DATE, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [roas_metric])
        monkeypatch.setattr(
            "app.modules.datasets.service.get_duckdb", lambda: duck
        )

        q = SemanticQuery(
            measures=["roas", "spend_sum"],
            dimensions=["campaign"],
            order={"roas": "desc"},
        )
        rows = duckdb_backend.run_semantic_query_duckdb(q, catalog, TABLE)
        assert [r["campaign"] for r in rows] == ["Campaign C", "Campaign A", "Campaign B"]
        assert rows[0]["roas"] == pytest.approx(550.0 / 110.0)

    def test_measure_filter_becomes_having(self, dataset):
        cols = [
            _col("campaign", "campaign", ColumnType.TEXT, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        sql, params = compile_semantic_sql(
            SemanticQuery(
                measures=["spend_sum"], dimensions=["campaign"],
                filters=[SemanticFilter(member="spend_sum", operator="gt", values=[200])],
            ),
            catalog, TABLE,
        )
        assert "HAVING" in sql
        assert params == [200]

    def test_unknown_member_rejected(self, dataset):
        catalog = build_catalog(dataset, [_col("spend", "spend", ColumnType.FLOAT, metric=True)], [])
        with pytest.raises(UnknownMemberError):
            compile_semantic_sql(SemanticQuery(measures=["nope"]), catalog, TABLE)

    def test_original_name_mapping(self, duck, monkeypatch, dataset):
        # Semantic name differs from the original DuckDB column name.
        duck.execute(f'ALTER TABLE {TABLE} RENAME campaign TO "Campaign Name"')
        cols = [
            _col("Campaign Name", "campaign_name", ColumnType.TEXT, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["spend_sum"], dimensions=["campaign_name"]),
            catalog, TABLE,
        )
        assert {r["campaign_name"] for r in rows} == {"Campaign A", "Campaign B", "Campaign C"}


class TestRawMeasures:
    def test_raw_member_in_catalog(self, catalog):
        assert catalog.measures["spend"].agg is None
        assert catalog.measures["spend_sum"].agg == "SUM"

    def test_raw_skipped_when_dimension_collides(self, dataset):
        cols = [_col("score", "score", ColumnType.FLOAT, metric=True, dim=True)]
        catalog = build_catalog(dataset, cols, [])
        assert "score" in catalog.dimensions
        assert "score" not in catalog.measures
        assert "score_sum" in catalog.measures

    def test_as_dict_exposes_agg(self, catalog):
        by_name = {r["name"]: r for r in catalog.as_dict()["measures"]}
        assert by_name["spend"]["agg"] is None
        assert by_name["spend_sum"]["agg"] == "SUM"

    def test_cube_rejects_raw(self, catalog):
        with pytest.raises(UnknownMemberError, match="local engine"):
            resolve_cube_query(SemanticQuery(measures=["spend"]), catalog)

    def test_cube_rejects_ohlc(self, catalog):
        with pytest.raises(UnknownMemberError, match="local engine"):
            resolve_cube_query(SemanticQuery(measures=["spend_sum"], mode="ohlc"), catalog)

    def test_mixed_raw_and_agg_rejected(self, dataset):
        catalog = build_catalog(dataset, [_col("spend", "spend", ColumnType.FLOAT, metric=True)], [])
        with pytest.raises(UnknownMemberError, match="mix raw"):
            compile_semantic_sql(SemanticQuery(measures=["spend", "spend_sum"]), catalog, TABLE)

    def test_detail_mode_no_group_by(self, duck, monkeypatch, dataset):
        cols = [
            _col("campaign", "campaign", ColumnType.TEXT, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        sql, _ = compile_semantic_sql(
            SemanticQuery(measures=["spend"], dimensions=["campaign"]), catalog, TABLE
        )
        assert "GROUP BY" not in sql
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["spend"], dimensions=["campaign"]), catalog, TABLE
        )
        assert len(rows) == 6  # every raw row, no aggregation
        assert {"campaign", "spend"} <= set(rows[0])

    def test_raw_measure_filter_goes_where(self, dataset):
        catalog = build_catalog(dataset, [_col("spend", "spend", ColumnType.FLOAT, metric=True)], [])
        sql, params = compile_semantic_sql(
            SemanticQuery(
                measures=["spend"],
                filters=[SemanticFilter(member="spend", operator="gt", values=[100])],
            ),
            catalog, TABLE,
        )
        assert "WHERE" in sql and "HAVING" not in sql
        assert params == [100]

    def test_raw_line_uses_full_timestamp_and_orders_chronologically(self, dataset):
        cols = [
            _col("date", "date", ColumnType.DATE, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        sql, _ = compile_semantic_sql(
            SemanticQuery(measures=["spend"], time_dimension="date", granularity="day"),
            catalog, TABLE,
        )
        # Detail mode: raw timestamp (no DATE_TRUNC), no GROUP BY, ordered by time.
        assert "DATE_TRUNC" not in sql
        assert "GROUP BY" not in sql
        assert 'ORDER BY "date" ASC' in sql


ROW_LEVEL_EXPR = {
    "type": "formula",
    "root": {
        "type": "binary", "op": "-",
        "left": {"type": "agg", "agg": "none", "column": "revenue"},
        "right": {"type": "agg", "agg": "none", "column": "spend"},
    },
}


class TestRowLevelComputedMetric:
    def _metric(self):
        return SemanticMetric(
            id=uuid.uuid4(), dataset_id=DS_ID, name="net", display_name="Net (row)",
            expression=ROW_LEVEL_EXPR,
        )

    def test_catalog_flags_row_level(self, dataset):
        cols = [
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [self._metric()])
        assert catalog.measures["net"].row_level is True
        # a normal ratio metric is NOT row-level
        assert catalog.measures["spend_sum"].row_level is False

    def test_cube_skips_row_level_metric(self, dataset, columns):
        model = build_cube_for_dataset(dataset, columns, [self._metric()])
        assert "net" not in {m["name"] for m in model["measures"]}

    def test_cube_query_rejects_row_level(self, dataset):
        cols = [
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [self._metric()])
        with pytest.raises(UnknownMemberError, match="local engine"):
            resolve_cube_query(SemanticQuery(measures=["net"]), catalog)

    def test_detail_query_returns_per_row_values(self, duck, monkeypatch, dataset):
        cols = [
            _col("campaign", "campaign", ColumnType.TEXT, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [self._metric()])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["net"], dimensions=["campaign"]), catalog, TABLE
        )
        assert len(rows) == 6  # per-row, no aggregation
        # Campaign A row 1: revenue 400 - spend 100 = 300
        first = next(r for r in rows if r["campaign"] == "Campaign A")
        assert first["net"] == pytest.approx(300.0)

    def test_row_level_cannot_mix_with_aggregate(self, dataset):
        cols = [
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [self._metric()])
        with pytest.raises(UnknownMemberError, match="mix raw"):
            compile_semantic_sql(SemanticQuery(measures=["net", "spend_sum"]), catalog, TABLE)


class TestOhlc:
    @pytest.fixture()
    def ohlc_catalog(self, dataset):
        cols = [
            _col("ts", "ts", ColumnType.DATETIME, dim=True),
            _col("price", "price", ColumnType.FLOAT, metric=True),
        ]
        return build_catalog(dataset, cols, [])

    def test_requires_raw_time_and_granularity(self, ohlc_catalog):
        with pytest.raises(UnknownMemberError, match="raw"):
            compile_ohlc_sql(
                SemanticQuery(measures=["price_sum"], time_dimension="ts", granularity="day", mode="ohlc"),
                ohlc_catalog, TABLE,
            )
        with pytest.raises(UnknownMemberError, match="time"):
            compile_ohlc_sql(
                SemanticQuery(measures=["price"], granularity="day", mode="ohlc"),
                ohlc_catalog, TABLE,
            )
        with pytest.raises(UnknownMemberError, match="granularity"):
            compile_ohlc_sql(
                SemanticQuery(measures=["price"], time_dimension="ts", mode="ohlc"),
                ohlc_catalog, TABLE,
            )
        with pytest.raises(UnknownMemberError, match="dimensions"):
            compile_ohlc_sql(
                SemanticQuery(
                    measures=["price"], dimensions=["ts"],
                    time_dimension="ts", granularity="day", mode="ohlc",
                ),
                ohlc_catalog, TABLE,
            )

    def test_open_close_high_low(self, duck, monkeypatch, dataset, ohlc_catalog):
        duck.execute("CREATE TABLE ohlc_t (ts TIMESTAMP, price DOUBLE)")
        duck.executemany("INSERT INTO ohlc_t VALUES (?, ?)", [
            ("2025-01-01 09:00:00", 10.0),
            ("2025-01-01 12:00:00", 30.0),
            ("2025-01-01 17:00:00", 20.0),
            ("2025-01-02 09:00:00", 25.0),
            ("2025-01-02 17:00:00", 5.0),
        ])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["price"], time_dimension="ts", granularity="day", mode="ohlc"),
            ohlc_catalog, "ohlc_t",
        )
        assert len(rows) == 2
        day1, day2 = rows
        assert (day1["open"], day1["high"], day1["low"], day1["close"]) == (10.0, 30.0, 10.0, 20.0)
        assert (day2["open"], day2["high"], day2["low"], day2["close"]) == (25.0, 25.0, 5.0, 5.0)

    def test_date_only_column_gives_distinct_open_close(self, duck, monkeypatch, dataset):
        # Regression: with a DATE column every row in a day bucket has the
        # same timestamp — arg_min/arg_max tied and open == close. first/last
        # ordered by (ts, rowid) must pick the first and last inserted rows.
        cols = [
            _col("date", "date", ColumnType.DATE, dim=True),
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["spend"], time_dimension="date", granularity="day", mode="ohlc"),
            catalog, TABLE,
        )
        # conftest day 1 insertion order: A(100), B(200), C(50); day 2: A(120), B(180), C(60)
        day1, day2 = rows
        assert (day1["open"], day1["high"], day1["low"], day1["close"]) == (100.0, 200.0, 50.0, 50.0)
        assert (day2["open"], day2["high"], day2["low"], day2["close"]) == (120.0, 180.0, 60.0, 60.0)
        assert day1["open"] != day1["close"]  # the reported symptom


PROFIT_MARGIN_EXPR = {
    "type": "formula",
    "root": {
        "type": "binary", "op": "*",
        "left": {
            "type": "binary", "op": "/",
            "left": {
                "type": "binary", "op": "-",
                "left": {"type": "agg", "agg": "sum", "column": "revenue"},
                "right": {"type": "agg", "agg": "sum", "column": "spend"},
            },
            "right": {"type": "agg", "agg": "sum", "column": "revenue"},
        },
        "right": {"type": "literal", "value": 100},
    },
}


class TestFormulaMetric:
    def _metric(self):
        return SemanticMetric(
            id=uuid.uuid4(), dataset_id=DS_ID, name="profit_margin",
            display_name="Profit Margin %", expression=PROFIT_MARGIN_EXPR,
        )

    def test_end_to_end_on_duckdb(self, duck, monkeypatch, dataset):
        cols = [
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [self._metric()])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        rows = duckdb_backend.run_semantic_query_duckdb(
            SemanticQuery(measures=["profit_margin"]), catalog, TABLE
        )
        # totals: spend 710, revenue 2000 → (2000-710)/2000*100 = 64.5
        assert rows[0]["profit_margin"] == pytest.approx(64.5)

    def test_compiled_into_cube_yaml(self, dataset, columns):
        model = build_cube_for_dataset(dataset, columns, [self._metric()])
        measure = next(m for m in model["measures"] if m["name"] == "profit_margin")
        assert measure["type"] == "number"
        assert "NULLIF" in measure["sql"] and 'SUM("revenue")' in measure["sql"]

    def test_preview_metric_value(self, duck, monkeypatch, dataset):
        cols = [
            _col("spend", "spend", ColumnType.FLOAT, metric=True),
            _col("revenue", "revenue", ColumnType.FLOAT, metric=True),
        ]
        catalog = build_catalog(dataset, cols, [])
        monkeypatch.setattr("app.modules.datasets.service.get_duckdb", lambda: duck)
        value = duckdb_backend.preview_metric_value(PROFIT_MARGIN_EXPR, catalog, TABLE)
        assert value == pytest.approx(64.5)
