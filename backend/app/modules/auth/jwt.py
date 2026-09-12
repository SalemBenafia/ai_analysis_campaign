"""
app/modules/auth/jwt.py
========================
JWT creation, verification, and HTTP-only cookie helpers.
Tokens are NEVER returned in response bodies — only in HttpOnly cookies.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Request, Response
from jose import JWTError, jwt

from app.core.settings import settings


class TokenClaims:
    PRINCIPAL_ID = "sub"
    PRINCIPAL_TYPE = "principal_type"
    ROLES = "roles"
    JTI = "jti"
    TYPE = "type"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _make_token(payload: dict, expire_minutes: int) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        **payload,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(principal_id: str, principal_type: str, roles: list[str]) -> str:
    return _make_token(
        {
            TokenClaims.PRINCIPAL_ID: principal_id,
            TokenClaims.PRINCIPAL_TYPE: principal_type,
            TokenClaims.ROLES: roles,
            TokenClaims.TYPE: "access",
        },
        expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )


def create_refresh_token(principal_id: str, principal_type: str) -> tuple[str, str]:
    jti = secrets.token_urlsafe(32)
    token = _make_token(
        {
            TokenClaims.PRINCIPAL_ID: principal_id,
            TokenClaims.PRINCIPAL_TYPE: principal_type,
            TokenClaims.JTI: jti,
            TokenClaims.TYPE: "refresh",
        },
        expire_minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60,
    )
    return token, jti


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return {}


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    _common = {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "domain": settings.COOKIE_DOMAIN,
    }
    response.set_cookie(
        settings.ACCESS_COOKIE_NAME, access,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/", **_common,
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME, refresh,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/", **_common,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")


def get_refresh_token_from_request(request: Request) -> Optional[str]:
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


def get_access_token_from_request(request: Request) -> Optional[str]:
    return request.cookies.get(settings.ACCESS_COOKIE_NAME)
