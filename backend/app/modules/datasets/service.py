"""
app/modules/datasets/service.py
=================================
Data ingestion service using Polars.
Reads CSV/Excel/JSON/Parquet, infers schema, loads into DuckDB.
No hard schema validation — supports arbitrary user data (see architecture spec).
"""
from __future__ import annotations

import io
import re
import uuid
from typing import Any

import duckdb
import polars as pl
import structlog

from app.core.settings import settings
from app.db.models import ColumnType, DatasetColumn, DatasetStatus

logger = structlog.get_logger()

_DUCKDB_CONN: duckdb.DuckDBPyConnection | None = None


def fetch_dicts(cursor) -> list[dict[str, Any]]:
    """
    Convert a DuckDB result to a list of row dicts using Polars (no pandas
    dependency). Date/datetime values become strings for safe JSON encoding.
    """
    df = cursor.pl()
    for name, dtype in zip(df.columns, df.dtypes):
        if dtype in (pl.Date, pl.Datetime, pl.Time, pl.Duration):
            df = df.with_columns(pl.col(name).cast(pl.Utf8))
    return df.to_dicts()


def get_duckdb() -> duckdb.DuckDBPyConnection:
    global _DUCKDB_CONN
    if _DUCKDB_CONN is None:
        _DUCKDB_CONN = duckdb.connect(
            settings.DUCKDB_PATH,
            config={
                "memory_limit": settings.DUCKDB_MEMORY_LIMIT,
                "threads": settings.DUCKDB_THREADS,
            },
        )
    return _DUCKDB_CONN


def _sanitize_table_name(name: str, dataset_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "_", name.lower())[:40]
    short_id = dataset_id.replace("-", "")[:8]
    return f"ds_{slug}_{short_id}"


def _infer_column_type(dtype: pl.DataType) -> ColumnType:
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return ColumnType.INTEGER
    if dtype in (pl.Float32, pl.Float64):
        return ColumnType.FLOAT
    if dtype == pl.Boolean:
        return ColumnType.BOOLEAN
    if dtype == pl.Date:
        return ColumnType.DATE
    if dtype in (pl.Datetime, pl.Duration):
        return ColumnType.DATETIME
    return ColumnType.TEXT


def parse_file(raw: bytes, filename: str) -> pl.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        return pl.read_csv(
            io.BytesIO(raw), infer_schema_length=1000, ignore_errors=True,
            try_parse_dates=True,
        )
    if ext in ("xlsx", "xls"):
        return pl.read_excel(io.BytesIO(raw))
    if ext == "json":
        return pl.read_json(io.BytesIO(raw))
    if ext == "parquet":
        return pl.read_parquet(io.BytesIO(raw))
    raise ValueError(f"Unsupported file format: {ext}")


def sanitize_semantic_name(name: str, taken: set[str]) -> str:
    """
    snake_case member name valid for Cube (^[a-zA-Z][a-zA-Z0-9_]*$),
    deduplicated against already-assigned names.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    if not slug or not slug[0].isalpha():
        slug = f"col_{slug}" if slug else "col"
    base, i = slug, 2
    while slug in taken:
        slug = f"{base}_{i}"
        i += 1
    taken.add(slug)
    return slug


def write_processed_parquet(df: pl.DataFrame, dataset_id: str) -> str:
    """Write the parsed dataframe as parquet to MinIO (original column names)."""
    from app.modules.storage.object_store import upload_bytes

    buf = io.BytesIO()
    df.write_parquet(buf)
    key = f"processed/{dataset_id}/data.parquet"
    upload_bytes(settings.MINIO_BUCKET_DATASETS, key, buf.getvalue(), "application/octet-stream")
    logger.info("Processed parquet written", key=key, rows=len(df))
    return key


def load_into_duckdb(df: pl.DataFrame, dataset_id: str, dataset_name: str) -> str:
    table_name = _sanitize_table_name(dataset_name, dataset_id)
    conn = get_duckdb()
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
    logger.info("Dataset loaded into DuckDB", table=table_name, rows=len(df))
    return table_name


def build_column_records(df: pl.DataFrame, dataset_id: str) -> list[dict]:
    columns = []
    taken: set[str] = set()
    for i, (name, dtype) in enumerate(zip(df.columns, df.dtypes)):
        col_type = _infer_column_type(dtype)
        series = df[name].drop_nulls()
        is_metric = col_type in (ColumnType.INTEGER, ColumnType.FLOAT)
        is_dimension = (
            col_type in (ColumnType.DATE, ColumnType.DATETIME, ColumnType.BOOLEAN)
            or (col_type == ColumnType.TEXT and series.n_unique() < 100)
        )

        sample = [str(v) for v in series.head(5).to_list()]

        columns.append({
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "semantic_name": sanitize_semantic_name(name, taken),
            "col_type": col_type,
            "position": i,
            "is_metric": is_metric,
            "is_dimension": is_dimension,
            "sample_values": sample,
            "null_count": int(df[name].is_null().sum()),
            "unique_count": int(df[name].n_unique()),
        })
    return columns


def run_query(sql: str, max_rows: int = 10_000) -> list[dict[str, Any]]:
    conn = get_duckdb()
    return fetch_dicts(conn.execute(f"SELECT * FROM ({sql}) q LIMIT {max_rows}"))


def get_dataset_schema_summary(table_name: str) -> dict:
    from app.modules.analytics.sql_builder import quote_table
    conn = get_duckdb()
    try:
        table = quote_table(table_name)
        cols = fetch_dicts(conn.execute(f"DESCRIBE {table}"))
        sample = fetch_dicts(conn.execute(f"SELECT * FROM {table} LIMIT 3"))
        return {
            "table": table_name,
            "columns": cols,
            "sample_rows": sample,
        }
    except Exception as e:
        return {"error": str(e)}
