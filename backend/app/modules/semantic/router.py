"""
app/modules/semantic/router.py
================================
User-facing semantic layer API:
  - member catalog per dataset (builder field panel)
  - semantic query execution (builder canvas, dashboards, insights)
  - computed metric CRUD + column semantic flags (semantic model editor)
Every model mutation bumps the Cube schema version.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import DatasetColumn, SemanticMetric, User
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.semantic.formula import (
    FormulaError,
    expression_is_row_level,
    validate_formula,
)
from app.modules.semantic.registry import bump_schema_version, get_catalog
from app.modules.semantic.schemas import SemanticQuery
from app.modules.semantic.service import get_owned_dataset, run_semantic_query

router = APIRouter(tags=["Semantic"])

_MEMBER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@router.get("/datasets/{dataset_id}/semantic")
async def get_members(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await get_owned_dataset(db, user, dataset_id)
    catalog = await get_catalog(db, ds)

    metrics_result = await db.execute(
        select(SemanticMetric).where(SemanticMetric.dataset_id == ds.id)
    )
    computed = [
        {
            "id": str(m.id),
            "name": m.name,
            "display_name": m.display_name,
            "description": m.description,
            "expression": m.expression,
            "format": m.format,
            "is_auto": m.is_auto,
            "is_row_level": expression_is_row_level(m.expression),
        }
        for m in metrics_result.scalars().all()
    ]

    return success({**catalog.as_dict(), "computed_metrics": computed})


class SemanticQueryRequest(SemanticQuery):
    dataset_id: uuid.UUID


@router.post("/semantic/query")
async def semantic_query(
    payload: SemanticQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = SemanticQuery(**payload.model_dump(exclude={"dataset_id"}))
    result = await run_semantic_query(db, user, payload.dataset_id, query)
    return success(result)


# ─── Computed metric CRUD ─────────────────────────────────────────────────────


class ExpressionPart(BaseModel):
    agg: str = "sum"
    column: str


class MetricExpression(BaseModel):
    type: str = "ratio"  # ratio | aggregate | formula
    numerator: ExpressionPart | None = None
    denominator: ExpressionPart | None = None
    multiplier: float = 1
    agg: str | None = None
    column: str | None = None
    root: dict | None = None  # formula AST — see semantic/formula.py

    def to_stored(self) -> dict:
        if self.type == "ratio":
            if not self.numerator or not self.denominator:
                raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": "Ratio needs numerator and denominator."})
            expr: dict = {
                "type": "ratio",
                "numerator": self.numerator.model_dump(),
                "denominator": self.denominator.model_dump(),
            }
            if self.multiplier != 1:
                expr["multiplier"] = self.multiplier
            return expr
        if self.type == "aggregate":
            if not self.column:
                raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": "Aggregate needs a column."})
            return {"type": "aggregate", "agg": self.agg or "sum", "column": self.column}
        if self.type == "formula":
            if not self.root:
                raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": "Formula needs a root node."})
            return {"type": "formula", "root": self.root}
        raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": f"Unsupported type {self.type!r}."})


class CreateMetricRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    display_name: str
    description: str | None = None
    expression: MetricExpression
    format: str | None = None


def _validate_expression_columns(expression: dict, valid_columns: set[str]) -> None:
    if expression.get("type") == "formula":
        try:
            validate_formula(expression.get("root") or {}, valid_columns)
        except FormulaError as e:
            raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": str(e)})
        return

    parts = []
    if expression.get("type") == "ratio":
        parts = [expression["numerator"], expression["denominator"]]
    elif expression.get("type") == "aggregate":
        parts = [expression]
    for part in parts:
        if part.get("column") not in valid_columns:
            raise HTTPException(400, detail={
                "code": "INVALID_EXPRESSION",
                "message": f"Unknown column {part.get('column')!r} in metric expression.",
            })


@router.post("/datasets/{dataset_id}/metrics", status_code=status.HTTP_201_CREATED)
async def create_metric(
    dataset_id: uuid.UUID,
    payload: CreateMetricRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await get_owned_dataset(db, user, dataset_id)

    name = payload.name.strip().lower()
    if not _MEMBER_NAME_RE.match(name):
        raise HTTPException(400, detail={"code": "INVALID_NAME", "message": "Metric name must be snake_case starting with a letter."})

    cols_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
    )
    valid_columns = {c.semantic_name or c.name for c in cols_result.scalars().all()}
    expression = payload.expression.to_stored()
    _validate_expression_columns(expression, valid_columns)

    existing = await db.execute(
        select(SemanticMetric).where(
            SemanticMetric.dataset_id == ds.id, SemanticMetric.name == name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail={"code": "DUPLICATE", "message": f"Metric {name!r} already exists."})

    metric = SemanticMetric(
        dataset_id=ds.id,
        name=name,
        display_name=payload.display_name,
        description=payload.description,
        expression=expression,
        format=payload.format,
        is_auto=False,
    )
    db.add(metric)
    await db.commit()
    await bump_schema_version()
    return success({"id": str(metric.id), "name": metric.name}, "Metric created.")


class MetricPreviewRequest(BaseModel):
    expression: MetricExpression


@router.post("/datasets/{dataset_id}/metrics/preview")
async def preview_metric(
    dataset_id: uuid.UUID,
    payload: MetricPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a metric expression over the whole dataset (dialog live preview)."""
    from app.modules.semantic.duckdb_backend import preview_metric_value
    from app.modules.semantic.registry import UnknownMemberError

    ds = await get_owned_dataset(db, user, dataset_id)
    cols_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
    )
    valid_columns = {c.semantic_name or c.name for c in cols_result.scalars().all()}
    expression = payload.expression.to_stored()
    _validate_expression_columns(expression, valid_columns)

    catalog = await get_catalog(db, ds)
    try:
        value = preview_metric_value(expression, catalog, ds.duckdb_table)
    except (UnknownMemberError, FormulaError) as e:
        raise HTTPException(400, detail={"code": "INVALID_EXPRESSION", "message": str(e)})
    except Exception as e:
        raise HTTPException(400, detail={"code": "PREVIEW_FAILED", "message": str(e)})
    return success({"value": value})


class UpdateMetricRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    expression: MetricExpression | None = None
    format: str | None = None


@router.patch("/datasets/{dataset_id}/metrics/{metric_id}")
async def update_metric(
    dataset_id: uuid.UUID,
    metric_id: uuid.UUID,
    payload: UpdateMetricRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await get_owned_dataset(db, user, dataset_id)
    result = await db.execute(
        select(SemanticMetric).where(
            SemanticMetric.id == metric_id, SemanticMetric.dataset_id == ds.id
        )
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Metric not found."})

    if payload.display_name is not None:
        metric.display_name = payload.display_name
    if payload.description is not None:
        metric.description = payload.description
    if payload.format is not None:
        metric.format = payload.format
    if payload.expression is not None:
        cols_result = await db.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )
        valid_columns = {c.semantic_name or c.name for c in cols_result.scalars().all()}
        expression = payload.expression.to_stored()
        _validate_expression_columns(expression, valid_columns)
        metric.expression = expression
        metric.is_auto = False

    await db.commit()
    await bump_schema_version()
    return success({}, "Metric updated.")


@router.delete("/datasets/{dataset_id}/metrics/{metric_id}")
async def delete_metric(
    dataset_id: uuid.UUID,
    metric_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await get_owned_dataset(db, user, dataset_id)
    result = await db.execute(
        select(SemanticMetric).where(
            SemanticMetric.id == metric_id, SemanticMetric.dataset_id == ds.id
        )
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Metric not found."})

    await db.delete(metric)
    await db.commit()
    await bump_schema_version()
    return success({}, "Metric deleted.")


# ─── Column semantic flags ────────────────────────────────────────────────────


class UpdateColumnRequest(BaseModel):
    display_name: str | None = None
    is_metric: bool | None = None
    is_dimension: bool | None = None


@router.patch("/datasets/{dataset_id}/columns/{column_id}")
async def update_column(
    dataset_id: uuid.UUID,
    column_id: uuid.UUID,
    payload: UpdateColumnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await get_owned_dataset(db, user, dataset_id)
    result = await db.execute(
        select(DatasetColumn).where(
            DatasetColumn.id == column_id, DatasetColumn.dataset_id == ds.id
        )
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Column not found."})

    if payload.display_name is not None:
        column.display_name = payload.display_name
    if payload.is_metric is not None:
        column.is_metric = payload.is_metric
    if payload.is_dimension is not None:
        column.is_dimension = payload.is_dimension

    await db.commit()
    await bump_schema_version()
    return success({}, "Column updated.")
