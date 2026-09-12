"""
app/modules/insights/router.py — SavedInsight CRUD + execute + discovery + NL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import (
    Dataset, DatasetColumn, DatasetStatus, InsightType, SavedInsight, User,
)
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.insights.engine import run_full_discovery
from app.modules.insights.service import execute_insight, nl_to_definition
from app.modules.semantic.registry import get_catalog
from app.modules.visualization.chart_rules import validate_definition

router = APIRouter(prefix="/insights", tags=["Insights"])


async def _enforce_chart_rules(db: AsyncSession, ds: Dataset, definition: object) -> None:
    """Reject v2 definitions whose shape doesn't fit their chart type."""
    if not isinstance(definition, dict) or not definition.get("visualization"):
        return
    catalog = await get_catalog(db, ds)
    messages = validate_definition(definition, catalog)
    if messages:
        raise HTTPException(400, detail={
            "code": "CHART_RULES_VIOLATION",
            "message": "; ".join(messages),
            "messages": messages,
        })


class CreateInsightRequest(BaseModel):
    dataset_id: uuid.UUID
    name: str
    description: str | None = None
    insight_type: InsightType = InsightType.CUSTOM
    insight_definition: dict
    tags: list[str] | None = None


def _insight_row(i: SavedInsight) -> dict:
    return {
        "id": str(i.id),
        "name": i.name,
        "description": i.description,
        "dataset_id": str(i.dataset_id) if i.dataset_id else None,
        "insight_type": i.insight_type.value,
        "insight_definition": i.insight_definition,
        "echart_config": i.echart_config,
        "ai_explanation": i.ai_explanation,
        "ai_recommendation": i.ai_recommendation,
        "is_pinned": i.is_pinned,
        "is_template": i.is_template,
        "tags": i.tags,
        "created_at": i.created_at.isoformat(),
    }


async def _get_owned_insight(insight_id: uuid.UUID, user: User, db: AsyncSession) -> SavedInsight:
    result = await db.execute(
        select(SavedInsight).where(
            SavedInsight.id == insight_id,
            SavedInsight.owner_id == user.id,
            SavedInsight.is_deleted.is_(False),
        )
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Insight not found."})
    return insight


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_insight(
    payload: CreateInsightRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == payload.dataset_id,
            Dataset.owner_id == user.id,
            Dataset.is_deleted.is_(False),
        )
    )
    ds = ds_result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    await _enforce_chart_rules(db, ds, payload.insight_definition)

    insight = SavedInsight(
        owner_id=user.id,
        dataset_id=payload.dataset_id,
        name=payload.name,
        description=payload.description,
        insight_type=payload.insight_type,
        insight_definition=payload.insight_definition,
        tags=payload.tags or [],
    )
    db.add(insight)
    await db.commit()
    return success({"id": str(insight.id), "name": insight.name}, "Insight saved.")


@router.get("/")
async def list_insights(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedInsight).where(
            SavedInsight.owner_id == user.id,
            SavedInsight.is_deleted.is_(False),
            SavedInsight.is_template.is_(False),
        ).order_by(SavedInsight.is_pinned.desc(), SavedInsight.created_at.desc())
    )
    return success({"insights": [_insight_row(i) for i in result.scalars().all()]})


@router.get("/templates")
async def list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedInsight).where(
            SavedInsight.is_template.is_(True),
            SavedInsight.is_deleted.is_(False),
        ).order_by(SavedInsight.created_at.desc())
    )
    return success({"templates": [_insight_row(i) for i in result.scalars().all()]})


@router.post("/{insight_id}/execute")
async def execute(
    insight_id: uuid.UUID,
    explain: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    insight = await _get_owned_insight(insight_id, user, db)
    result = await execute_insight(db, user, insight, explain=explain)
    return success(result)


class UpdateInsightRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    insight_definition: dict | None = None
    tags: list[str] | None = None
    is_pinned: bool | None = None


@router.patch("/{insight_id}")
async def update_insight(
    insight_id: uuid.UUID,
    payload: UpdateInsightRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    insight = await _get_owned_insight(insight_id, user, db)
    if payload.name is not None:
        insight.name = payload.name
    if payload.description is not None:
        insight.description = payload.description
    if payload.insight_definition is not None:
        if insight.dataset_id:
            ds_result = await db.execute(
                select(Dataset).where(
                    Dataset.id == insight.dataset_id,
                    Dataset.owner_id == user.id,
                    Dataset.is_deleted.is_(False),
                )
            )
            ds = ds_result.scalar_one_or_none()
            if ds:
                await _enforce_chart_rules(db, ds, payload.insight_definition)
        insight.insight_definition = payload.insight_definition
    if payload.tags is not None:
        insight.tags = payload.tags
    if payload.is_pinned is not None:
        insight.is_pinned = payload.is_pinned
    await db.commit()
    return success(_insight_row(insight), "Insight updated.")


class NLCreateRequest(BaseModel):
    dataset_id: uuid.UUID
    prompt: str


@router.post("/nl-create")
async def nl_create(
    payload: NLCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await nl_to_definition(db, user, payload.dataset_id, payload.prompt)
    return success(result)


@router.post("/{dataset_id}/discover")
async def auto_discover(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.owner_id == user.id,
            Dataset.status == DatasetStatus.READY,
        )
    )
    ds = ds_result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    cols_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id)
    )
    cols = cols_result.scalars().all()
    metrics = [c.name for c in cols if c.is_metric]
    dims = [c.name for c in cols if c.is_dimension]
    date_cols = [c.name for c in cols if c.col_type.value in ("date", "datetime")]
    allowed = {c.name for c in cols}

    findings = run_full_discovery(
        ds.duckdb_table, metrics, dims, allowed, date_cols[0] if date_cols else None
    )
    return success({"findings": findings})


@router.delete("/{insight_id}")
async def delete_insight(
    insight_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    insight = await _get_owned_insight(insight_id, user, db)
    insight.is_deleted = True
    insight.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return success({}, "Insight deleted.")
