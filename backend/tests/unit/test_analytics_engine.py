"""Analytics engine correctness against a hand-verifiable fixture dataset."""
from __future__ import annotations

import pytest

import app.modules.analytics.engine as engine
from tests.conftest import TABLE


@pytest.fixture(autouse=True)
def _patch_duckdb(monkeypatch, duck):
    monkeypatch.setattr(engine, "get_duckdb", lambda: duck)


class TestComputeKpis:
    def test_sums_and_avgs(self, allowed_columns):
        kpis = engine.compute_kpis(TABLE, ["spend", "revenue"], allowed_columns)
        assert kpis["spend_sum"] == pytest.approx(710.0)
        assert kpis["revenue_sum"] == pytest.approx(2000.0)
        assert kpis["spend_avg"] == pytest.approx(710.0 / 6)

    def test_empty_metrics(self, allowed_columns):
        assert engine.compute_kpis(TABLE, [], allowed_columns) == {}


class TestGroupBy:
    def test_group_by_sum_desc(self, allowed_columns):
        rows = engine.group_by_metric(TABLE, "campaign", "spend", allowed_columns)
        assert [r["campaign"] for r in rows] == ["Campaign B", "Campaign A", "Campaign C"]
        assert rows[0]["value"] == pytest.approx(380.0)

    def test_filters_are_applied(self, allowed_columns):
        rows = engine.group_by_metric(
            TABLE, "campaign", "spend", allowed_columns,
            filters=[{"field": "country", "operator": "=", "value": "US"}],
        )
        assert len(rows) == 1
        assert rows[0]["campaign"] == "Campaign A"

    def test_injection_via_dimension_raises(self, allowed_columns):
        with pytest.raises(Exception):
            engine.group_by_metric(
                TABLE, 'campaign"; DROP TABLE x; --', "spend", allowed_columns
            )


class TestTimeSeries:
    def test_daily_series(self, allowed_columns):
        rows = engine.time_series(TABLE, "date", "revenue", allowed_columns)
        assert len(rows) == 2
        assert rows[0]["value"] == pytest.approx(950.0)   # 400+300+250
        assert rows[1]["value"] == pytest.approx(1050.0)  # 480+270+300


class TestPeriodComparison:
    def test_delta_and_pct(self, allowed_columns):
        result = engine.period_comparison(
            TABLE, "date", "revenue",
            ("2025-01-01", "2025-01-01"),
            ("2025-01-02", "2025-01-02"),
            allowed_columns,
        )
        assert result["period_a"]["value"] == pytest.approx(950.0)
        assert result["period_b"]["value"] == pytest.approx(1050.0)
        assert result["direction"] == "up"


class TestAnomalies:
    def test_no_false_positives_on_flat_data(self, allowed_columns):
        rows = engine.detect_anomalies(TABLE, "spend", allowed_columns, threshold=3.0)
        assert rows == []
