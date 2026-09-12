"""
app/modules/copilot/router.py — AI Copilot REST endpoints.
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
    CopilotConversation, CopilotMessage, Dashboard, DashboardWidget, Dataset,
    DatasetColumn, DatasetStatus, InsightType, MessageRole, SavedInsight, User,
    VisualizationType,
)
from app.db.session import get_db
from app.modules.admin.ai_usage import record_ai_usage
from app.modules.auth.dependencies import get_current_user
from app.modules.copilot.agent import run_copilot
from app.modules.copilot.tools import CopilotContext
from app.modules.datasets.service import get_dataset_schema_summary
from app.modules.semantic.registry import cube_name_for, get_catalog

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class StartConversationRequest(BaseModel):
    dataset_id: uuid.UUID
    title: str | None = None


class SendMessageRequest(BaseModel):
    message: str


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def start_conversation(
    payload: StartConversationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == payload.dataset_id,
            Dataset.owner_id == user.id,
            Dataset.status == DatasetStatus.READY,
        )
    )
    ds = ds_result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found or not ready."})

    schema = get_dataset_schema_summary(ds.duckdb_table)

    conv = CopilotConversation(
        user_id=user.id,
        dataset_id=payload.dataset_id,
        title=payload.title or f"Analysis of {ds.name}",
        context=schema,
    )
    db.add(conv)
    await db.commit()
    return success({"conversation_id": str(conv.id), "title": conv.title}, "Conversation started.")


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(
        select(CopilotConversation).where(
            CopilotConversation.id == conversation_id,
            CopilotConversation.user_id == user.id,
            CopilotConversation.is_deleted.is_(False),
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Conversation not found."})

    ds_result = await db.execute(select(Dataset).where(Dataset.id == conv.dataset_id))
    ds = ds_result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset for this conversation is gone."})

    cols_result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
    )
    allowed_columns = {c.name for c in cols_result.scalars().all()}
    catalog = await get_catalog(db, ds)

    ctx = CopilotContext(
        dataset_id=str(ds.id),
        dataset_table=ds.duckdb_table or "",
        allowed_columns=allowed_columns,
        cube_name=cube_name_for(ds),
        members=catalog.as_dict(),
        user_id=str(user.id),
    )

    history_result = await db.execute(
        select(CopilotMessage).where(CopilotMessage.conversation_id == conversation_id)
        .order_by(CopilotMessage.created_at.asc())
    )
    history = [
        {"role": m.role.value, "content": m.content}
        for m in history_result.scalars().all()
    ]

    import time
    start = time.perf_counter()
    response = await run_copilot(
        user_message=payload.message,
        history=history,
        ctx=ctx,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    user_msg = CopilotMessage(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=payload.message,
    )
    ai_msg = CopilotMessage(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=response["text"],
        echart_config=response.get("echart_config"),
        semantic_query=response.get("semantic_query"),
        tool_calls=response.get("tool_calls", []),
        latency_ms=latency_ms,
    )
    db.add(user_msg)
    db.add(ai_msg)
    await db.commit()

    usage = response.get("usage") or {}
    await record_ai_usage(
        db,
        user_id=user.id,
        feature="copilot",
        model=usage.get("model"),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        latency_ms=latency_ms,
        success=not response.get("rate_limited"),
    )

    return success({
        "message_id": str(ai_msg.id),
        "text": response["text"],
        "echart_config": response.get("echart_config"),
        "semantic_query": response.get("semantic_query"),
        "tool_calls": response.get("tool_calls", []),
        "latency_ms": latency_ms,
    })


@router.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CopilotConversation).where(
            CopilotConversation.user_id == user.id,
            CopilotConversation.is_deleted.is_(False),
        ).order_by(CopilotConversation.created_at.desc()).limit(20)
    )
    conversations = result.scalars().all()
    return success({
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "dataset_id": str(c.dataset_id) if c.dataset_id else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in conversations
        ]
    })


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(
        select(CopilotConversation).where(
            CopilotConversation.id == conversation_id,
            CopilotConversation.user_id == user.id,
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Conversation not found."})

    msgs_result = await db.execute(
        select(CopilotMessage).where(CopilotMessage.conversation_id == conversation_id)
        .order_by(CopilotMessage.created_at.asc())
    )
    return success({
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "echart_config": m.echart_config,
                "semantic_query": m.semantic_query,
                "tool_calls": m.tool_calls,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs_result.scalars().all()
        ]
    })


async def _get_message_for_user(
    message_id: uuid.UUID, user: User, db: AsyncSession
) -> tuple[CopilotMessage, CopilotConversation]:
    result = await db.execute(
        select(CopilotMessage, CopilotConversation)
        .join(CopilotConversation, CopilotMessage.conversation_id == CopilotConversation.id)
        .where(
            CopilotMessage.id == message_id,
            CopilotConversation.user_id == user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Message not found."})
    return row[0], row[1]


class SaveInsightRequest(BaseModel):
    name: str
    description: str | None = None


@router.post("/messages/{message_id}/save-insight", status_code=status.HTTP_201_CREATED)
async def save_message_as_insight(
    message_id: uuid.UUID,
    payload: SaveInsightRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg, conv = await _get_message_for_user(message_id, user, db)
    if not msg.semantic_query:
        raise HTTPException(400, detail={"code": "NO_QUERY", "message": "This answer has no semantic query to save."})

    definition = {**msg.semantic_query, "version": 2, "visualization": _viz_from_echart(msg.echart_config)}
    insight = SavedInsight(
        owner_id=user.id,
        dataset_id=conv.dataset_id,
        name=payload.name,
        description=payload.description,
        insight_type=InsightType.AI_GENERATED,
        insight_definition=definition,
        echart_config=msg.echart_config,
    )
    db.add(insight)
    await db.commit()
    return success({"id": str(insight.id), "name": insight.name}, "Saved as insight.")


class AddToDashboardRequest(BaseModel):
    dashboard_id: uuid.UUID
    title: str


@router.post("/messages/{message_id}/add-to-dashboard", status_code=status.HTTP_201_CREATED)
async def add_message_to_dashboard(
    message_id: uuid.UUID,
    payload: AddToDashboardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg, conv = await _get_message_for_user(message_id, user, db)
    if not msg.semantic_query:
        raise HTTPException(400, detail={"code": "NO_QUERY", "message": "This answer has no semantic query to add."})

    dash_result = await db.execute(
        select(Dashboard).where(
            Dashboard.id == payload.dashboard_id,
            Dashboard.owner_id == user.id,
            Dashboard.is_deleted.is_(False),
        )
    )
    if not dash_result.scalar_one_or_none():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dashboard not found."})

    viz = _viz_from_echart(msg.echart_config)
    widget = DashboardWidget(
        dashboard_id=payload.dashboard_id,
        dataset_id=conv.dataset_id,
        title=payload.title,
        viz_type=VisualizationType(viz) if viz in VisualizationType._value2member_map_ else VisualizationType.BAR,
        semantic_query=msg.semantic_query,
        echart_config=msg.echart_config or {},
    )
    db.add(widget)
    await db.commit()
    return success({"widget_id": str(widget.id)}, "Added to dashboard.")


def _viz_from_echart(echart: dict | None) -> str:
    if not echart:
        return "bar"
    if echart.get("type") in ("kpi", "table"):
        return echart["type"]
    series = echart.get("series") or []
    if series and isinstance(series, list):
        stype = series[0].get("type")
        if stype == "line" and series[0].get("areaStyle"):
            return "area"
        if stype in ("bar", "line", "pie", "scatter", "candlestick"):
            return stype
    return "bar"
