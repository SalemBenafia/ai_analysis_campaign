"""
app/modules/semantic/cube_client.py
=====================================
The backend is the only Cube client. It signs a short-lived JWT carrying the
tenancy context ({user_id, dataset_cubes}) that cube.js's queryRewrite
enforces, POSTs to /cubejs-api/v1/load and handles Cube's "Continue wait"
long-poll protocol with a bounded budget.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from jose import jwt

from app.core.settings import settings

logger = structlog.get_logger()


class CubeUnavailableError(RuntimeError):
    """Cube is down, misconfigured or exceeded its wait budget."""


def sign_token(user_id: str, dataset_cubes: list[str]) -> str:
    if not settings.CUBEJS_API_SECRET:
        raise CubeUnavailableError("CUBEJS_API_SECRET is not configured")
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "dataset_cubes": dataset_cubes,
        "iat": now,
        "exp": now + timedelta(seconds=60),
    }
    return jwt.encode(payload, settings.CUBEJS_API_SECRET, algorithm="HS256")


async def load(query: dict, user_id: str, dataset_cubes: list[str]) -> list[dict[str, Any]]:
    """Run a Cube query, returning normalized-agnostic raw rows."""
    token = sign_token(user_id, dataset_cubes)
    url = f"{settings.CUBE_API_URL}/cubejs-api/v1/load"
    deadline = time.monotonic() + settings.CUBE_LOAD_TIMEOUT

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                resp = await client.post(
                    url,
                    json={"query": query},
                    headers={"Authorization": token},
                )
            except httpx.HTTPError as e:
                raise CubeUnavailableError(f"Cube unreachable: {e}") from e

            if resp.status_code >= 500:
                raise CubeUnavailableError(f"Cube error {resp.status_code}: {resp.text[:300]}")

            body = resp.json()

            if isinstance(body, dict) and body.get("error") == "Continue wait":
                if time.monotonic() > deadline:
                    raise CubeUnavailableError("Cube query exceeded wait budget")
                await asyncio.sleep(1.0)
                continue

            if resp.status_code != 200:
                # 4xx — bad query or tenancy rejection; not a fallback case.
                message = body.get("error", resp.text[:300]) if isinstance(body, dict) else resp.text[:300]
                raise ValueError(f"Cube rejected query: {message}")

            return body.get("data", [])


async def warm_up() -> None:
    """Best-effort /meta request so Cube recompiles the schema immediately."""
    try:
        token = sign_token("system", [])
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(
                f"{settings.CUBE_API_URL}/cubejs-api/v1/meta",
                headers={"Authorization": token},
            )
    except Exception as e:
        logger.debug("Cube warm-up skipped", error=str(e))
