"""
app/modules/datasets/transform.py
===================================
Transform step of ingestion: processed parquet (original column names) →
marts parquet (semantic snake_case names, deduplicated). The marts parquet
is what Cube's DuckDB driver reads from MinIO.

Primary path: dbt-duckdb (generic stg_dataset model, parameterized per
dataset). Fallback: Polars, producing the identical output contract, so
ingestion never depends on dbt being healthy.
"""
from __future__ import annotations

import io
import json

import anyio
import polars as pl
import structlog

from app.core.settings import settings
from app.modules.storage.object_store import download_bytes, upload_bytes

logger = structlog.get_logger()


def _s3_path(key: str) -> str:
    return f"s3://{settings.MINIO_BUCKET_DATASETS}/{key}"


def _run_dbt_sync(source_key: str, target_key: str, column_map: dict[str, str]) -> None:
    from dbt.cli.main import dbtRunner

    dbt_vars = {
        "source_path": _s3_path(source_key),
        "target_path": _s3_path(target_key),
        "column_map": column_map,
    }
    result = dbtRunner().invoke([
        "run",
        "--select", "stg_dataset",
        "--project-dir", settings.DBT_PROJECT_DIR,
        "--profiles-dir", f"{settings.DBT_PROJECT_DIR}/profiles",
        "--vars", json.dumps(dbt_vars),
    ])
    if not result.success:
        raise RuntimeError(f"dbt run failed: {result.exception or 'see dbt logs'}")


def transform_with_polars(source_key: str, target_key: str, column_map: dict[str, str]) -> None:
    """Same contract as the dbt model: rename to semantic names + dedupe."""
    raw = download_bytes(settings.MINIO_BUCKET_DATASETS, source_key)
    df = pl.read_parquet(io.BytesIO(raw))
    df = df.rename({orig: sem for orig, sem in column_map.items() if orig in df.columns})
    df = df.unique(maintain_order=True)
    buf = io.BytesIO()
    df.write_parquet(buf)
    upload_bytes(settings.MINIO_BUCKET_DATASETS, target_key, buf.getvalue())


async def run_transform(
    dataset_id: str, source_key: str, column_map: dict[str, str]
) -> tuple[str, str]:
    """
    Produce the marts parquet for a dataset.
    Returns (marts_key, engine_used) where engine_used is "dbt" or "polars".
    """
    target_key = f"marts/{dataset_id}/clean.parquet"

    if settings.DBT_ENABLED:
        try:
            await anyio.to_thread.run_sync(
                _run_dbt_sync, source_key, target_key, column_map
            )
            logger.info("Transform complete (dbt)", dataset_id=dataset_id, key=target_key)
            return target_key, "dbt"
        except Exception as e:
            logger.warning(
                "dbt transform failed — falling back to Polars",
                dataset_id=dataset_id, error=str(e),
            )

    await anyio.to_thread.run_sync(
        transform_with_polars, source_key, target_key, column_map
    )
    logger.info("Transform complete (polars)", dataset_id=dataset_id, key=target_key)
    return target_key, "polars"
