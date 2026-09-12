"""
app/modules/datasets/router.py — Dataset CRUD + file upload endpoints.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.core.settings import settings
from app.db.models import ColumnType, Dataset, DatasetColumn, DatasetStatus, User
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.datasets.service import (
    build_column_records,
    get_dataset_schema_summary,
    load_into_duckdb,
    parse_file,
    run_query,
)
from app.modules.storage.object_store import upload_bytes

router = APIRouter(prefix="/datasets", tags=["Datasets"])

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json", "parquet"}
MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


def _dataset_row(ds: Dataset) -> dict:
    return {
        "id": str(ds.id),
        "name": ds.name,
        "description": ds.description,
        "file_name": ds.file_name,
        "file_format": ds.file_format,
        "file_size_bytes": ds.file_size_bytes,
        "status": ds.status.value,
        "row_count": ds.row_count,
        "column_count": ds.column_count,
        "duckdb_table": ds.duckdb_table,
        "created_at": ds.created_at.isoformat(),
    }


async def _process_dataset(dataset_id: str, raw: bytes, filename: str) -> None:
    """
    Background ingestion pipeline:
    parse → local DuckDB → column records → processed parquet (MinIO)
    → dbt/polars transform → marts parquet → auto metrics (ROAS/CTR/…)
    → READY → bump Cube schema version.
    """
    from app.db.session import AsyncSessionLocal
    from app.db.models import DatasetColumn as Col
    from app.modules.datasets.service import write_processed_parquet
    from app.modules.datasets.transform import run_transform

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        ds = result.scalar_one_or_none()
        if not ds:
            return
        try:
            df = parse_file(raw, filename)
            table_name = load_into_duckdb(df, dataset_id, ds.name)
            col_records = build_column_records(df, dataset_id)

            ds.row_count = len(df)
            ds.column_count = len(df.columns)
            ds.duckdb_table = table_name

            columns = []
            for rec in col_records:
                col = Col(dataset_id=uuid.UUID(dataset_id), **rec)
                db.add(col)
                columns.append(col)

            # Parquet pipeline feeding the Cube semantic layer. Failure here
            # degrades gracefully: the dataset still works on local DuckDB.
            try:
                ds.parquet_key = write_processed_parquet(df, dataset_id)
                column_map = {rec["name"]: rec["semantic_name"] for rec in col_records}
                marts_key, engine_used = await run_transform(
                    dataset_id, ds.parquet_key, column_map
                )
                ds.marts_key = marts_key
                ds.meta = {**(ds.meta or {}), "transform": engine_used}
            except Exception as e:
                ds.meta = {**(ds.meta or {}), "transform": "failed", "transform_error": str(e)}

            ds.status = DatasetStatus.READY
            await db.commit()

            # Auto-detect computed metrics (ROAS/CTR/CPA/…) and notify Cube.
            try:
                from app.modules.semantic.metrics_autodetect import autodetect_metrics
                from app.modules.semantic.registry import bump_schema_version

                await autodetect_metrics(db, ds, columns)
                await bump_schema_version()
            except Exception as e:
                import structlog
                structlog.get_logger().warning(
                    "Semantic post-processing failed", dataset_id=dataset_id, error=str(e)
                )
        except Exception as e:
            ds.status = DatasetStatus.ERROR
            ds.error_message = str(e)
            await db.commit()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail={"code": "INVALID_FORMAT", "message": f"Supported formats: {ALLOWED_EXTENSIONS}"})

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": f"Max {settings.MAX_UPLOAD_MB}MB"})

    ds = Dataset(
        owner_id=user.id,
        name=file.filename.rsplit(".", 1)[0],
        file_name=file.filename,
        file_format=ext,
        file_size_bytes=len(raw),
        status=DatasetStatus.PROCESSING,
    )
    db.add(ds)
    await db.flush()
    dataset_id = str(ds.id)

    minio_key = f"datasets/{dataset_id}/{file.filename}"
    try:
        upload_bytes(settings.MINIO_BUCKET_DATASETS, minio_key, raw)
        ds.minio_key = minio_key
    except Exception:
        pass

    await db.commit()

    background_tasks.add_task(_process_dataset, dataset_id, raw, file.filename)
    return success({"dataset": _dataset_row(ds)}, "Dataset upload started.")


@router.get("/")
async def list_datasets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dataset).where(Dataset.owner_id == user.id, Dataset.is_deleted.is_(False))
        .order_by(Dataset.created_at.desc())
    )
    datasets = result.scalars().all()
    return success({"datasets": [_dataset_row(ds) for ds in datasets]})


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user.id, Dataset.is_deleted.is_(False))
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    col_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id).order_by(DatasetColumn.position)
    )
    cols = col_result.scalars().all()

    return success({
        "dataset": _dataset_row(ds),
        "columns": [
            {
                "id": str(c.id),
                "name": c.name,
                "display_name": c.display_name,
                "semantic_name": c.semantic_name,
                "col_type": c.col_type.value,
                "is_metric": c.is_metric,
                "is_dimension": c.is_dimension,
                "sample_values": c.sample_values,
                "null_count": c.null_count,
                "unique_count": c.unique_count,
            }
            for c in cols
        ],
        "schema_summary": get_dataset_schema_summary(ds.duckdb_table) if ds.duckdb_table else None,
    })


@router.delete("/{dataset_id}", status_code=status.HTTP_200_OK)
async def delete_dataset(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user.id, Dataset.is_deleted.is_(False))
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    from datetime import datetime, timezone
    ds.is_deleted = True
    ds.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return success({}, "Dataset deleted.")


class QueryRequest(BaseModel):
    sql: str


@router.post("/{dataset_id}/query")
async def query_dataset(
    dataset_id: uuid.UUID,
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user.id, Dataset.status == DatasetStatus.READY)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found or not ready."})

    from app.modules.analytics.sql_builder import UnsafeSQLError, validate_select

    try:
        sql = validate_select(payload.sql.strip(), ds.duckdb_table)
    except UnsafeSQLError as e:
        raise HTTPException(400, detail={"code": "INVALID_SQL", "message": str(e)})

    try:
        rows = run_query(sql, max_rows=settings.MAX_QUERY_ROWS)
        return success({"rows": rows, "row_count": len(rows)})
    except Exception as e:
        raise HTTPException(400, detail={"code": "QUERY_ERROR", "message": str(e)})


@router.get("/{dataset_id}/preview")
async def preview_dataset(
    dataset_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    filters: str | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated raw-row preview of the dataset (local DuckDB).

    filters: URL-encoded JSON array of {"field", "operator", "value"} —
             columns validated against the dataset's schema, values bound
             as parameters (compile_filters).
    search:  case-insensitive substring match across all text columns.
    """
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user.id, Dataset.status == DatasetStatus.READY)
    )
    ds = result.scalar_one_or_none()
    if not ds or not ds.duckdb_table:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found or not ready."})

    from app.modules.analytics.sql_builder import (
        UnsafeIdentifierError, UnsafeSQLError, compile_filters, quote_ident, quote_table,
    )
    from app.modules.datasets.service import fetch_dicts, get_duckdb

    cols_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
    )
    dataset_columns = list(cols_result.scalars().all())
    allowed = {c.name for c in dataset_columns}

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where_parts: list[str] = []
    params: list = []
    try:
        if filters:
            try:
                parsed = json.loads(filters)
            except json.JSONDecodeError:
                raise UnsafeSQLError("filters must be a JSON array")
            if not isinstance(parsed, list):
                raise UnsafeSQLError("filters must be a JSON array")
            clause, filter_params = compile_filters(parsed, allowed)
            if clause:
                where_parts.append(clause.removeprefix("WHERE "))
                params.extend(filter_params)

        if search and search.strip():
            text_cols = [c.name for c in dataset_columns if c.col_type == ColumnType.TEXT] or list(allowed)
            ors = " OR ".join(f"CAST({quote_ident(c, allowed)} AS VARCHAR) ILIKE ?" for c in text_cols)
            where_parts.append(f"({ors})")
            params.extend([f"%{search.strip()}%"] * len(text_cols))
    except (UnsafeIdentifierError, UnsafeSQLError) as e:
        raise HTTPException(400, detail={"code": "INVALID_FILTER", "message": str(e)})

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    table = quote_table(ds.duckdb_table)

    try:
        conn = get_duckdb()
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table}{where_sql}", params
        ).fetchone()[0]
        cursor = conn.execute(
            f"SELECT * FROM {table}{where_sql} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        columns = [d[0] for d in cursor.description]
        rows = fetch_dicts(cursor)
        return success({
            "rows": rows,
            "columns": columns,
            "offset": offset,
            "limit": limit,
            "total_rows": total,
            "unfiltered_rows": ds.row_count,
        })
    except Exception as e:
        raise HTTPException(400, detail={"code": "QUERY_ERROR", "message": str(e)})
