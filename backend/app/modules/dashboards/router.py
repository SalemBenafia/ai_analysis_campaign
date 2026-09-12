"""
app/modules/dashboards/router.py — Dashboard + widget management (live data).
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
    Dashboard, DashboardWidget, Dataset, SavedInsight, User, VisualizationType,
)
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.semantic.registry import get_catalog
from app.modules.semantic.schemas import SemanticQuery
from app.modules.semantic.service import run_semantic_query
from app.modules.visualization.chart_rules import validate_definition
from app.modules.visualization.echarts import build_from_definition

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


async def _enforce_widget_chart_rules(
    db: AsyncSession,
    user: User,
    dataset_id: uuid.UUID | None,
    viz_type: VisualizationType,
    semantic_query: dict | None,
) -> None:
    """Reject live widgets whose query shape doesn't fit their chart type."""
    if not semantic_query or not dataset_id:
        return
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.owner_id == user.id,
            Dataset.is_deleted.is_(False),
        )
    )
    ds = ds_result.scalar_one_or_none()
    if not ds:
        return
    catalog = await get_catalog(db, ds)
    definition = {**semantic_query, "visualization": viz_type.value}
    messages = validate_definition(definition, catalog)
    if messages:
        raise HTTPException(400, detail={
            "code": "CHART_RULES_VIOLATION",
            "message": "; ".join(messages),
            "messages": messages,
        })


class CreateDashboardRequest(BaseModel):
    name: str
    description: str | None = None
    is_default: bool = False


class UpdateDashboardRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None


class CreateWidgetRequest(BaseModel):
    title: str
    dataset_id: uuid.UUID | None = None
    insight_id: uuid.UUID | None = None
    viz_type: VisualizationType = VisualizationType.BAR
    semantic_query: dict | None = None
    echart_config: dict | None = None
    query_sql: str | None = None
    filters: dict | None = None
    position: dict = {"x": 0, "y": 0, "w": 6, "h": 4}
    refresh_interval: int | None = None


class UpdateWidgetRequest(BaseModel):
    title: str | None = None
    viz_type: VisualizationType | None = None
    semantic_query: dict | None = None
    position: dict | None = None
    refresh_interval: int | None = None


class LayoutItem(BaseModel):
    widget_id: uuid.UUID
    x: int
    y: int
    w: int
    h: int


class SaveLayoutRequest(BaseModel):
    items: list[LayoutItem]


def _dash_row(d: Dashboard) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "description": d.description,
        "is_default": d.is_default,
        "layout": d.layout,
        "created_at": d.created_at.isoformat(),
    }


def _widget_row(w: DashboardWidget) -> dict:
    return {
        "id": str(w.id),
        "title": w.title,
        "viz_type": w.viz_type.value,
        "echart_config": w.echart_config,
        "semantic_query": w.semantic_query,
        "position": w.position,
        "refresh_interval": w.refresh_interval,
        "dataset_id": str(w.dataset_id) if w.dataset_id else None,
        "insight_id": str(w.insight_id) if w.insight_id else None,
    }


async def _get_owned_dashboard(dashboard_id: uuid.UUID, user: User, db: AsyncSession) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(
            Dashboard.id == dashboard_id,
            Dashboard.owner_id == user.id,
            Dashboard.is_deleted.is_(False),
        )
    )
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dashboard not found."})
    return dashboard


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: CreateDashboardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard = Dashboard(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
    )
    db.add(dashboard)
    await db.commit()
    return success({"dashboard": _dash_row(dashboard)}, "Dashboard created.")


@router.get("/")
async def list_dashboards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dashboard).where(
            Dashboard.owner_id == user.id,
            Dashboard.is_deleted.is_(False),
        ).order_by(Dashboard.is_default.desc(), Dashboard.created_at.desc())
    )
    return success({"dashboards": [_dash_row(d) for d in result.scalars().all()]})


@router.get("/{dashboard_id}")
async def get_dashboard(
    dashboard_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await _get_owned_dashboard(dashboard_id, user, db)
    widgets_result = await db.execute(
        select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
    )
    widgets = [_widget_row(w) for w in widgets_result.scalars().all()]
    return success({"dashboard": _dash_row(dashboard), "widgets": widgets})


@router.patch("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: UpdateDashboardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await _get_owned_dashboard(dashboard_id, user, db)
    if payload.name is not None:
        dashboard.name = payload.name
    if payload.description is not None:
        dashboard.description = payload.description
    if payload.is_default is not None:
        dashboard.is_default = payload.is_default
    await db.commit()
    return success(_dash_row(dashboard), "Dashboard updated.")


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await _get_owned_dashboard(dashboard_id, user, db)
    dashboard.is_deleted = True
    dashboard.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return success({}, "Dashboard deleted.")


@router.put("/{dashboard_id}/layout")
async def save_layout(
    dashboard_id: uuid.UUID,
    payload: SaveLayoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await _get_owned_dashboard(dashboard_id, user, db)
    widgets_result = await db.execute(
        select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
    )
    widgets = {w.id: w for w in widgets_result.scalars().all()}

    for item in payload.items:
        widget = widgets.get(item.widget_id)
        if widget:
            widget.position = {"x": item.x, "y": item.y, "w": item.w, "h": item.h}

    dashboard.layout = {
        "cols": 12,
        "rows": [item.model_dump() | {"widget_id": str(item.widget_id)} for item in payload.items],
    }
    await db.commit()
    return success({}, "Layout saved.")


@router.post("/{dashboard_id}/widgets", status_code=status.HTTP_201_CREATED)
async def add_widget(
    dashboard_id: uuid.UUID,
    payload: CreateWidgetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_dashboard(dashboard_id, user, db)

    dataset_id = payload.dataset_id
    semantic_query = payload.semantic_query

    # A widget sourced from an insight inherits its dataset + definition.
    if payload.insight_id:
        ins_result = await db.execute(
            select(SavedInsight).where(
                SavedInsight.id == payload.insight_id,
                SavedInsight.owner_id == user.id,
                SavedInsight.is_deleted.is_(False),
            )
        )
        insight = ins_result.scalar_one_or_none()
        if not insight:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Insight not found."})
        dataset_id = insight.dataset_id

    await _enforce_widget_chart_rules(db, user, dataset_id, payload.viz_type, semantic_query)

    widget = DashboardWidget(
        dashboard_id=dashboard_id,
        dataset_id=dataset_id,
        insight_id=payload.insight_id,
        title=payload.title,
        viz_type=payload.viz_type,
        semantic_query=semantic_query,
        echart_config=payload.echart_config or {},
        query_sql=payload.query_sql,
        filters=payload.filters or {},
        position=payload.position,
        refresh_interval=payload.refresh_interval,
    )
    db.add(widget)
    await db.commit()
    return success({"widget_id": str(widget.id)}, "Widget added.")


async def _get_owned_widget(
    dashboard_id: uuid.UUID, widget_id: uuid.UUID, user: User, db: AsyncSession
) -> DashboardWidget:
    await _get_owned_dashboard(dashboard_id, user, db)
    result = await db.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id,
            DashboardWidget.dashboard_id == dashboard_id,
        )
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Widget not found."})
    return widget


@router.patch("/{dashboard_id}/widgets/{widget_id}")
async def update_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    payload: UpdateWidgetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    widget = await _get_owned_widget(dashboard_id, widget_id, user, db)
    if payload.viz_type is not None or payload.semantic_query is not None:
        await _enforce_widget_chart_rules(
            db, user, widget.dataset_id,
            payload.viz_type or widget.viz_type,
            payload.semantic_query or widget.semantic_query,
        )
    if payload.title is not None:
        widget.title = payload.title
    if payload.viz_type is not None:
        widget.viz_type = payload.viz_type
    if payload.semantic_query is not None:
        widget.semantic_query = payload.semantic_query
    if payload.position is not None:
        widget.position = payload.position
    if payload.refresh_interval is not None:
        widget.refresh_interval = payload.refresh_interval
    await db.commit()
    return success(_widget_row(widget), "Widget updated.")


@router.delete("/{dashboard_id}/widgets/{widget_id}")
async def delete_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    widget = await _get_owned_widget(dashboard_id, widget_id, user, db)
    await db.delete(widget)
    await db.commit()
    return success({}, "Widget removed.")


@router.post("/{dashboard_id}/widgets/{widget_id}/data")
async def widget_data(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a widget's live data (from its insight or its semantic query)."""
    widget = await _get_owned_widget(dashboard_id, widget_id, user, db)

    definition: dict | None = None
    dataset_id = widget.dataset_id

    if widget.insight_id:
        ins_result = await db.execute(
            select(SavedInsight).where(
                SavedInsight.id == widget.insight_id,
                SavedInsight.owner_id == user.id,
                SavedInsight.is_deleted.is_(False),
            )
        )
        insight = ins_result.scalar_one_or_none()
        if not insight:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Source insight not found."})
        from app.modules.insights.service import execute_insight
        result = await execute_insight(db, user, insight, explain=False)
        return success({"rows": result["rows"], "echart_config": result["echart_config"], "meta": result["meta"]})

    if widget.semantic_query and dataset_id:
        definition = widget.semantic_query
        query = SemanticQuery(**{k: v for k, v in definition.items() if k in SemanticQuery.model_fields})
        result = await run_semantic_query(db, user, dataset_id, query)
        echart = build_from_definition(
            result["rows"], {**definition, "title": widget.title, "visualization": widget.viz_type.value}
        )
        return success({"rows": result["rows"], "echart_config": echart, "meta": result["meta"]})

    # Static widget — return its cached config as-is.
    return success({"rows": [], "echart_config": widget.echart_config or {}, "meta": {"engine": "static"}})
