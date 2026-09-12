"""
app/modules/analytics/router.py — Analytics API endpoints.

All engine calls receive the dataset's real column set so identifiers are
validated before touching DuckDB (see sql_builder).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import Dataset, DatasetColumn, DatasetStatus, User
from app.db.session import get_db
from app.modules.analytics.engine import (
    compute_kpis,
    detect_anomalies,
    group_by_metric,
    period_comparison,
    time_series,
)
from app.modules.analytics.sql_builder import UnsafeIdentifierError, UnsafeSQLError
from app.modules.auth.dependencies import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _get_ready_dataset(dataset_id: uuid.UUID, user: User, db: AsyncSession) -> Dataset:
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.owner_id == user.id,
            Dataset.status == DatasetStatus.READY,
            Dataset.is_deleted.is_(False),
        )
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found or not ready."})
    return ds


async def _get_columns(dataset_id: uuid.UUID, db: AsyncSession) -> list[DatasetColumn]:
    result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id)
    )
    return list(result.scalars().all())


@router.get("/{dataset_id}/kpis")
async def get_kpis(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_ready_dataset(dataset_id, user, db)
    cols = await _get_columns(dataset_id, db)
    metric_cols = [c.name for c in cols if c.is_metric]
    allowed = {c.name for c in cols}
    kpis = compute_kpis(ds.duckdb_table, metric_cols, allowed)
    return success({"kpis": kpis})


class GroupByRequest(BaseModel):
    dimension: str
    metric: str
    agg: str = "SUM"
    filters: list[dict] | None = None
    limit: int = 50
    order: str = "DESC"


@router.post("/{dataset_id}/group-by")
async def group_by(
    dataset_id: uuid.UUID,
    payload: GroupByRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_ready_dataset(dataset_id, user, db)
    cols = await _get_columns(dataset_id, db)
    allowed = {c.name for c in cols}
    try:
        rows = group_by_metric(
            ds.duckdb_table, payload.dimension, payload.metric, allowed,
            payload.agg, payload.filters, payload.limit, payload.order,
        )
    except (UnsafeIdentifierError, UnsafeSQLError) as e:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": str(e)})
    return success({"rows": rows})


class TimeSeriesRequest(BaseModel):
    date_col: str
    metric: str
    agg: str = "SUM"
    truncate: str = "day"
    filters: list[dict] | None = None


@router.post("/{dataset_id}/time-series")
async def get_time_series(
    dataset_id: uuid.UUID,
    payload: TimeSeriesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_ready_dataset(dataset_id, user, db)
    cols = await _get_columns(dataset_id, db)
    allowed = {c.name for c in cols}
    try:
        rows = time_series(
            ds.duckdb_table, payload.date_col, payload.metric, allowed,
            payload.agg, payload.truncate, payload.filters,
        )
    except (UnsafeIdentifierError, UnsafeSQLError) as e:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": str(e)})
    return success({"rows": rows})


@router.get("/{dataset_id}/anomalies")
async def get_anomalies(
    dataset_id: uuid.UUID,
    metric: str,
    threshold: float = 2.0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_ready_dataset(dataset_id, user, db)
    cols = await _get_columns(dataset_id, db)
    allowed = {c.name for c in cols}
    try:
        rows = detect_anomalies(ds.duckdb_table, metric, allowed, threshold)
    except (UnsafeIdentifierError, UnsafeSQLError) as e:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": str(e)})
    return success({"anomalies": rows})


class PeriodCompareRequest(BaseModel):
    date_col: str
    metric: str
    period_a: list[str]
    period_b: list[str]
    agg: str = "SUM"


@router.post("/{dataset_id}/compare")
async def compare_periods(
    dataset_id: uuid.UUID,
    payload: PeriodCompareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_ready_dataset(dataset_id, user, db)
    cols = await _get_columns(dataset_id, db)
    allowed = {c.name for c in cols}
    if len(payload.period_a) != 2 or len(payload.period_b) != 2:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": "Each period needs [start, end]."})
    try:
        result = period_comparison(
            ds.duckdb_table, payload.date_col, payload.metric,
            (payload.period_a[0], payload.period_a[1]),
            (payload.period_b[0], payload.period_b[1]),
            allowed, payload.agg,
        )
    except (UnsafeIdentifierError, UnsafeSQLError) as e:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": str(e)})
    return success(result)
