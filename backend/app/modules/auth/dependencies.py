"""
app/modules/auth/dependencies.py
==================================
FastAPI dependency injection for authenticated requests.
Reads access token from HttpOnly cookie (never from Authorization header).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser, User
from app.db.session import get_db
from app.modules.auth.jwt import TokenClaims, decode_token, get_access_token_from_request


@dataclass
class CurrentPrincipal:
    id: uuid.UUID
    email: str
    principal_type: str  # "user" | "admin"
    roles: list[str]


def _get_token_payload(request: Request) -> dict:
    token = get_access_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NO_TOKEN", "message": "Authentication required."},
        )
    payload = decode_token(token)
    if not payload or payload.get(TokenClaims.TYPE) != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token."},
        )
    return payload


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = _get_token_payload(request)
    if payload.get(TokenClaims.PRINCIPAL_TYPE) != "user":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "User access required."})

    result = await db.execute(
        select(User).where(
            User.id == payload[TokenClaims.PRINCIPAL_ID],
            User.is_deleted.is_(False),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail={"code": "USER_NOT_FOUND", "message": "User not found."})
    return user


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    payload = _get_token_payload(request)
    if payload.get(TokenClaims.PRINCIPAL_TYPE) != "admin":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Admin access required."})

    result = await db.execute(
        select(AdminUser).where(
            AdminUser.id == payload[TokenClaims.PRINCIPAL_ID],
            AdminUser.is_deleted.is_(False),
            AdminUser.is_active.is_(True),
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail={"code": "ADMIN_NOT_FOUND", "message": "Admin not found."})
    return admin


async def get_current_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentPrincipal:
    """Works for both users and admins. Use for shared endpoints."""
    payload = _get_token_payload(request)
    principal_type = payload.get(TokenClaims.PRINCIPAL_TYPE)
    principal_id = payload.get(TokenClaims.PRINCIPAL_ID)
    roles = payload.get(TokenClaims.ROLES, [])

    if principal_type == "admin":
        result = await db.execute(select(AdminUser).where(AdminUser.id == principal_id))
        entity = result.scalar_one_or_none()
        if entity:
            return CurrentPrincipal(
                id=entity.id, email=entity.email,
                principal_type="admin", roles=roles,
            )
    else:
        result = await db.execute(select(User).where(User.id == principal_id))
        entity = result.scalar_one_or_none()
        if entity:
            return CurrentPrincipal(
                id=entity.id, email=entity.email,
                principal_type="user", roles=roles,
            )

    raise HTTPException(status_code=401, detail={"code": "PRINCIPAL_NOT_FOUND", "message": "Principal not found."})
