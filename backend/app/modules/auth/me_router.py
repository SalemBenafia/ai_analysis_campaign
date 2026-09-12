"""app/modules/auth/me_router.py — /me endpoint for the current principal."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.schemas import success
from app.db.models import AdminUser, User
from app.modules.auth.dependencies import get_current_admin, get_current_user

router = APIRouter(prefix="/me", tags=["Me"])


@router.get("/")
async def get_me_user(user: User = Depends(get_current_user)):
    return success({
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "company": user.company,
        "avatar_url": user.avatar_url,
        "principal_type": "user",
        "roles": ["user"],
        "preferences": user.preferences,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    })


@router.get("/admin")
async def get_me_admin(admin: AdminUser = Depends(get_current_admin)):
    return success({
        "id": str(admin.id),
        "email": admin.email,
        "first_name": admin.first_name,
        "last_name": admin.last_name,
        "principal_type": "admin",
        "roles": [admin.role.value],
        "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
    })
