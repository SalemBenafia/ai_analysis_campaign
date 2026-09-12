"""
app/modules/admin/users/router.py — Admin user management endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import (
    AdminUser, AIUsageLog, CopilotConversation, CopilotMessage, Dashboard,
    Dataset, Report, SavedInsight, User,
)
from app.db.session import get_db
from app.modules.admin.audit import write_audit
from app.modules.auth.dependencies import get_current_admin

router = APIRouter(prefix="/admin/users", tags=["Admin — Users"])


@router.get("/")
async def list_users(
    page: int = 1,
    per_page: int = 20,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    result = await db.execute(
        select(User).where(User.is_deleted.is_(False))
        .order_by(User.created_at.desc())
        .offset(offset).limit(per_page)
    )
    total_result = await db.execute(
        select(func.count()).select_from(User).where(User.is_deleted.is_(False))
    )
    total = total_result.scalar_one()

    return success({
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "company": u.company,
                "is_active": u.is_active,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat(),
            }
            for u in result.scalars().all()
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@router.patch("/{user_id}/suspend")
async def suspend_user(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "User not found."})
    user.is_active = not user.is_active
    state = "suspended" if not user.is_active else "activated"
    await write_audit(
        db, admin, action=f"user.{state}", resource_type="user",
        resource_id=user.id, details={"email": user.email}, request=request,
    )
    await db.commit()
    return success({"is_active": user.is_active}, f"User {state}.")


@router.delete("/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "User not found."})
    user.is_deleted = True
    user.deleted_at = datetime.now(tz=timezone.utc)
    await write_audit(
        db, admin, action="user.deleted", resource_type="user",
        resource_id=user.id, details={"email": user.email}, request=request,
    )
    await db.commit()
    return success({}, "User deleted.")


@router.get("/stats")
async def get_user_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count()).select_from(User).where(User.is_deleted.is_(False)))).scalar()
    active_users = (await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True), User.is_deleted.is_(False)))).scalar()
    total_datasets = (await db.execute(select(func.count()).select_from(Dataset).where(Dataset.is_deleted.is_(False)))).scalar()
    total_reports = (await db.execute(select(func.count()).select_from(Report).where(Report.is_deleted.is_(False)))).scalar()

    return success({
        "total_users": total_users,
        "active_users": active_users,
        "total_datasets": total_datasets,
        "total_reports": total_reports,
    })


# NOTE: keep this route AFTER /stats — a {user_id} path defined earlier would
# capture "stats" and fail UUID validation.
@router.get("/{user_id}")
async def get_user_detail(
    user_id: uuid.UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Full profile + resource and AI-usage footprint for one user."""
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "User not found."})

    async def count(model, *where) -> int:
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar() or 0

    datasets_count, storage_bytes, total_rows = (await db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(Dataset.file_size_bytes), 0),
            func.coalesce(func.sum(Dataset.row_count), 0),
        ).where(Dataset.owner_id == user.id, Dataset.is_deleted.is_(False))
    )).one()

    messages_count = (await db.execute(
        select(func.count()).select_from(CopilotMessage)
        .join(CopilotConversation, CopilotConversation.id == CopilotMessage.conversation_id)
        .where(CopilotConversation.user_id == user.id)
    )).scalar() or 0

    ai_calls, ai_input, ai_output, ai_last = (await db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.max(AIUsageLog.created_at),
        ).where(AIUsageLog.user_id == user.id)
    )).one()

    recent_result = await db.execute(
        select(Dataset).where(Dataset.owner_id == user.id, Dataset.is_deleted.is_(False))
        .order_by(Dataset.created_at.desc()).limit(5)
    )
    recent_datasets = [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status.value,
            "row_count": d.row_count,
            "file_size_bytes": d.file_size_bytes,
            "created_at": d.created_at.isoformat(),
        }
        for d in recent_result.scalars().all()
    ]

    return success({
        "user": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "company": user.company,
            "avatar_url": user.avatar_url,
            "is_active": user.is_active,
            "preferences": user.preferences,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
        },
        "resources": {
            "datasets": datasets_count,
            "storage_bytes": int(storage_bytes),
            "dataset_rows": int(total_rows),
            "dashboards": await count(Dashboard, Dashboard.owner_id == user.id, Dashboard.is_deleted.is_(False)),
            "insights": await count(SavedInsight, SavedInsight.owner_id == user.id, SavedInsight.is_deleted.is_(False)),
            "reports": await count(Report, Report.owner_id == user.id, Report.is_deleted.is_(False)),
            "conversations": await count(CopilotConversation, CopilotConversation.user_id == user.id, CopilotConversation.is_deleted.is_(False)),
            "messages": messages_count,
        },
        "ai_usage": {
            "calls": ai_calls,
            "input_tokens": int(ai_input),
            "output_tokens": int(ai_output),
            "total_tokens": int(ai_input) + int(ai_output),
            "last_call_at": ai_last.isoformat() if ai_last else None,
        },
        "recent_datasets": recent_datasets,
    })
