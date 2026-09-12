"""
app/modules/auth/router.py
===========================
Unified authentication endpoints.

DESIGN DECISION (per spec):
  - ONE /auth/login endpoint — the backend determines the role from credentials.
  - Guest never chooses "user" or "admin" — this is inferred server-side.
  - Backend checks AdminUser table first, then User table.
  - JWT principal_type field encodes the role.
  - All tokens live in HttpOnly cookies only — never in response JSON.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.core.settings import settings
from app.db.models import AdminUser, RefreshToken, User
from app.db.session import get_db
from app.modules.auth.jwt import (
    TokenClaims,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_refresh_token_from_request,
    hash_password,
    set_auth_cookies,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    company: str | None = None



def _persist_refresh(db: AsyncSession, principal_id: str, principal_type: str, jti: str) -> None:
    db.add(RefreshToken(
        principal_id=principal_id,
        principal_type=principal_type,
        jti=jti,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))


def _user_response(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "company": u.company,
        "principal_type": "user",
        "roles": ["user"],
    }


def _admin_response(a: AdminUser) -> dict:
    return {
        "id": str(a.id),
        "email": a.email,
        "first_name": a.first_name,
        "last_name": a.last_name,
        "principal_type": "admin",
        "roles": [a.role.value],
    }


# ─── Registration (users only — admins are seeded) ────────────────────────────

@router.post("/register/", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where(User.email == payload.email, User.is_deleted.is_(False))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_TAKEN", "message": "An account with this email already exists."},
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        company=payload.company,
    )
    db.add(user)
    await db.flush()

    access = create_access_token(str(user.id), "user", ["user"])
    refresh, jti = create_refresh_token(str(user.id), "user")
    _persist_refresh(db, str(user.id), "user", jti)
    user.last_login_at = datetime.now(tz=timezone.utc)
    await db.commit()

    set_auth_cookies(response, access, refresh)
    return success({"principal": _user_response(user)}, "Account created.")


# ─── Unified Login — role inferred from credentials ──────────────────────────

@router.post("/login/")
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Single login endpoint. Tries AdminUser first, then User.
    The caller never specifies a role — the backend decides.
    """
    # 1. Check AdminUser table first
    admin_result = await db.execute(
        select(AdminUser).where(AdminUser.email == payload.email, AdminUser.is_deleted.is_(False))
    )
    admin = admin_result.scalar_one_or_none()
    if admin and verify_password(payload.password, admin.hashed_password):
        if not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_SUSPENDED", "message": "Admin account suspended."},
            )
        access = create_access_token(str(admin.id), "admin", [admin.role.value])
        refresh, jti = create_refresh_token(str(admin.id), "admin")
        _persist_refresh(db, str(admin.id), "admin", jti)
        admin.last_login_at = datetime.now(tz=timezone.utc)
        await db.commit()
        set_auth_cookies(response, access, refresh)
        return success({"principal": _admin_response(admin)}, "Login successful.")

    # 2. Check regular User table
    user_result = await db.execute(
        select(User).where(User.email == payload.email, User.is_deleted.is_(False))
    )
    user = user_result.scalar_one_or_none()
    if user and verify_password(payload.password, user.hashed_password):
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_SUSPENDED", "message": "Account suspended."},
            )
        access = create_access_token(str(user.id), "user", ["user"])
        refresh, jti = create_refresh_token(str(user.id), "user")
        _persist_refresh(db, str(user.id), "user", jti)
        user.last_login_at = datetime.now(tz=timezone.utc)
        await db.commit()
        set_auth_cookies(response, access, refresh)
        return success({"principal": _user_response(user)}, "Login successful.")

    # 3. No match in either table
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."},
    )


# ─── Token Refresh ────────────────────────────────────────────────────────────

@router.post("/token/refresh/")
async def refresh_tokens(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = get_refresh_token_from_request(request)
    if not refresh_token:
        raise HTTPException(status_code=401, detail={"code": "NO_REFRESH_TOKEN", "message": "Missing refresh token."})

    payload = decode_token(refresh_token)
    if payload.get(TokenClaims.TYPE) != "refresh":
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Expected refresh token."})

    jti = payload.get(TokenClaims.JTI)
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti, RefreshToken.is_revoked.is_(False)))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=401, detail={"code": "TOKEN_REVOKED", "message": "Refresh token revoked."})

    record.is_revoked = True
    principal_id = payload.get(TokenClaims.PRINCIPAL_ID)
    principal_type = payload.get(TokenClaims.PRINCIPAL_TYPE)

    roles: list[str] = []
    if principal_type == "admin":
        r = await db.execute(select(AdminUser).where(AdminUser.id == principal_id))
        a = r.scalar_one_or_none()
        if a:
            roles = [a.role.value]
    else:
        roles = ["user"]

    new_access = create_access_token(principal_id, principal_type, roles)
    new_refresh, new_jti = create_refresh_token(principal_id, principal_type)
    _persist_refresh(db, principal_id, principal_type, new_jti)
    await db.commit()

    set_auth_cookies(response, new_access, new_refresh)
    return success({}, "Token refreshed.")


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post("/logout/")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = get_refresh_token_from_request(request)
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get(TokenClaims.JTI)
            if jti:
                result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
                rec = result.scalar_one_or_none()
                if rec:
                    rec.is_revoked = True
                    await db.commit()
        except Exception:
            pass
    clear_auth_cookies(response)
    return success({}, "Logged out.")


