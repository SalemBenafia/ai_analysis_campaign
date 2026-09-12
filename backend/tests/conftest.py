"""
Shared pytest fixtures.

Unit tests run without any external service. The `duck` fixture provides an
in-memory DuckDB preloaded with a small marketing dataset whose aggregates
are easy to verify by hand.
"""
from __future__ import annotations

import duckdb
import pytest

# Columns mirror what a typical marketing CSV would produce after ingestion.
MARKETING_ROWS = [
    # campaign,   country, date,         spend, revenue, impressions, clicks, purchases
    ("Campaign A", "US", "2025-01-01", 100.0, 400.0, 10_000, 300, 20),
    ("Campaign A", "US", "2025-01-02", 120.0, 480.0, 11_000, 330, 24),
    ("Campaign B", "DE", "2025-01-01", 200.0, 300.0, 20_000, 250, 10),
    ("Campaign B", "DE", "2025-01-02", 180.0, 270.0, 19_000, 240, 9),
    ("Campaign C", "FR", "2025-01-01", 50.0, 250.0, 5_000, 200, 12),
    ("Campaign C", "FR", "2025-01-02", 60.0, 300.0, 6_000, 220, 14),
]

MARKETING_COLUMNS = [
    "campaign", "country", "date", "spend", "revenue", "impressions", "clicks", "purchases",
]

TABLE = "ds_test_12345678"


@pytest.fixture()
def duck() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(
        f"""
        CREATE TABLE {TABLE} (
            campaign VARCHAR, country VARCHAR, date DATE,
            spend DOUBLE, revenue DOUBLE,
            impressions BIGINT, clicks BIGINT, purchases BIGINT
        )
        """
    )
    conn.executemany(
        f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", MARKETING_ROWS
    )
    yield conn
    conn.close()


@pytest.fixture()
def allowed_columns() -> set[str]:
    return set(MARKETING_COLUMNS)
