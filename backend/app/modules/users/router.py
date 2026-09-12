"""
app/modules/users/router.py — User profile management endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import User
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.jwt import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["Users"])


class UpdateProfileRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return success({
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "company": user.company,
        "avatar_url": user.avatar_url,
        "preferences": user.preferences,
        "created_at": user.created_at.isoformat(),
    })


@router.patch("/profile")
async def update_profile(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.company is not None:
        user.company = payload.company
    await db.commit()
    return success({"first_name": user.first_name, "last_name": user.last_name}, "Profile updated.")


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail={"code": "WRONG_PASSWORD", "message": "Current password incorrect."})
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return success({}, "Password changed.")
