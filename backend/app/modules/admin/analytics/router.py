"""
app/modules/admin/analytics/router.py — Platform + AI usage analytics.

One overview endpoint feeds the whole admin analytics page: platform counts,
AI call/token totals, and the aggregates behind the charts (tokens per day,
per model, per feature, top consumers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import (
    AdminUser, AIUsageLog, CopilotConversation, CopilotMessage, Dashboard,
    Dataset, Report, SavedInsight, User,
)
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_admin

router = APIRouter(prefix="/admin/analytics", tags=["Admin — Analytics"])

_TOKENS = AIUsageLog.input_tokens + AIUsageLog.output_tokens


@router.get("/overview")
async def analytics_overview(
    days: int = 14,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    days = max(1, min(int(days), 90))
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=days)

    async def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        if where:
            stmt = stmt.where(*where)
        return (await db.execute(stmt)).scalar() or 0

    users = {
        "total": await count(User, User.is_deleted.is_(False)),
        "active": await count(User, User.is_deleted.is_(False), User.is_active.is_(True)),
        "new_7d": await count(
            User, User.is_deleted.is_(False), User.created_at >= now - timedelta(days=7)
        ),
    }

    content = {
        "datasets": await count(Dataset, Dataset.is_deleted.is_(False)),
        "insights": await count(SavedInsight, SavedInsight.is_deleted.is_(False)),
        "dashboards": await count(Dashboard, Dashboard.is_deleted.is_(False)),
        "reports": await count(Report, Report.is_deleted.is_(False)),
        "conversations": await count(CopilotConversation, CopilotConversation.is_deleted.is_(False)),
        "messages": await count(CopilotMessage),
    }

    total_calls, input_tokens, output_tokens, avg_latency, ok_calls = (await db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.avg(AIUsageLog.latency_ms),
            func.coalesce(func.sum(case((AIUsageLog.success.is_(True), 1), else_=0)), 0),
        )
    )).one()

    day = func.date_trunc("day", AIUsageLog.created_at)
    by_day = (await db.execute(
        select(
            day.label("day"),
            func.count(),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
        )
        .where(AIUsageLog.created_at >= since)
        .group_by(day).order_by(day)
    )).all()

    by_model = (await db.execute(
        select(
            AIUsageLog.model,
            func.count(),
            func.coalesce(func.sum(_TOKENS), 0),
        ).group_by(AIUsageLog.model).order_by(func.coalesce(func.sum(_TOKENS), 0).desc())
    )).all()

    by_feature = (await db.execute(
        select(
            AIUsageLog.feature,
            func.count(),
            func.coalesce(func.sum(_TOKENS), 0),
            func.avg(AIUsageLog.latency_ms),
        ).group_by(AIUsageLog.feature).order_by(func.count().desc())
    )).all()

    top_users = (await db.execute(
        select(
            User.email,
            func.count(),
            func.coalesce(func.sum(_TOKENS), 0),
        )
        .join(User, User.id == AIUsageLog.user_id)
        .group_by(User.email)
        .order_by(func.coalesce(func.sum(_TOKENS), 0).desc())
        .limit(8)
    )).all()

    return success({
        "users": users,
        "content": content,
        "ai": {
            "total_calls": total_calls,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(input_tokens) + int(output_tokens),
            "avg_latency_ms": round(float(avg_latency), 1) if avg_latency is not None else None,
            "success_rate": round(ok_calls / total_calls, 4) if total_calls else None,
            "calls_24h": await count(
                AIUsageLog, AIUsageLog.created_at >= now - timedelta(hours=24)
            ),
            "tokens_by_day": [
                {
                    "date": d.date().isoformat(),
                    "calls": calls,
                    "input_tokens": int(inp),
                    "output_tokens": int(out),
                }
                for d, calls, inp, out in by_day
            ],
            "by_model": [
                {"model": model or "(unknown)", "calls": calls, "tokens": int(tokens)}
                for model, calls, tokens in by_model
            ],
            "by_feature": [
                {
                    "feature": feature,
                    "calls": calls,
                    "tokens": int(tokens),
                    "avg_latency_ms": round(float(lat), 1) if lat is not None else None,
                }
                for feature, calls, tokens, lat in by_feature
            ],
            "top_users": [
                {"email": email, "calls": calls, "tokens": int(tokens)}
                for email, calls, tokens in top_users
            ],
        },
        "window_days": days,
    })
