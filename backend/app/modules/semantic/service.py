"""
app/modules/semantic/service.py
=================================
Single entry point for running semantic queries. Chooses the engine
(Cube or local DuckDB) per settings, with automatic fallback to DuckDB
when Cube is unreachable — so every consumer (builder, insights,
dashboard widgets, copilot) gets the same behavior.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.models import Dataset, DatasetStatus, User
from app.modules.semantic import cube_client
from app.modules.semantic.cube_client import CubeUnavailableError
from app.modules.semantic.duckdb_backend import run_semantic_query_duckdb
from app.modules.semantic.registry import (
    MemberCatalog,
    UnknownMemberError,
    get_catalog,
    normalize_cube_rows,
    resolve_cube_query,
)
from app.modules.semantic.schemas import SemanticQuery

logger = structlog.get_logger()


async def get_owned_dataset(
    db: AsyncSession, user: User, dataset_id: uuid.UUID
) -> Dataset:
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.owner_id == user.id,
            Dataset.status == DatasetStatus.READY,
            Dataset.is_deleted.is_(False),
        )
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found or not ready."})
    return ds


async def run_semantic_query(
    db: AsyncSession,
    user: User,
    dataset_id: uuid.UUID,
    query: SemanticQuery,
    catalog: MemberCatalog | None = None,
) -> dict[str, Any]:
    """Returns {"rows": [...], "meta": {"engine", "took_ms"}}."""
    ds = await get_owned_dataset(db, user, dataset_id)
    if catalog is None:
        catalog = await get_catalog(db, ds)

    start = time.perf_counter()
    engine = "duckdb"
    rows: list[dict]

    # Raw-column measures, row-level formula metrics and OHLC (candlestick)
    # queries only exist on the local engine — the generated Cube schema knows
    # aggregated members only.
    needs_local = query.mode == "ohlc" or any(
        (member := catalog.measures.get(m)) is not None and member.row_level
        for m in query.measures
    )
    use_cube = settings.SEMANTIC_ENGINE == "cube" and bool(ds.marts_key) and not needs_local
    try:
        if use_cube:
            try:
                cube_query = resolve_cube_query(query, catalog)
                raw = await cube_client.load(cube_query, str(user.id), [catalog.cube_name])
                rows = normalize_cube_rows(raw, catalog)
                engine = "cube"
            except CubeUnavailableError as e:
                logger.warning("Cube unavailable — falling back to DuckDB", error=str(e))
                rows = run_semantic_query_duckdb(query, catalog, ds.duckdb_table)
        else:
            rows = run_semantic_query_duckdb(query, catalog, ds.duckdb_table)
    except UnknownMemberError as e:
        raise HTTPException(400, detail={"code": "UNKNOWN_MEMBER", "message": str(e)})
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, detail={"code": "INVALID_QUERY", "message": str(e)})

    took_ms = int((time.perf_counter() - start) * 1000)
    return {"rows": rows, "meta": {"engine": engine, "took_ms": took_ms}}
