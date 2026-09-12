"""
app/modules/semantic/internal_router.py
=========================================
Endpoints consumed ONLY by the Cube container (repositoryFactory +
schemaVersion in cube/cube.js). Guarded by a shared internal token, not
user cookies. Responses are raw JSON (no success() envelope) because
cube.js consumes them directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.models import Dataset, DatasetColumn, DatasetStatus, SemanticMetric
from app.db.session import get_db
from app.modules.semantic.cube_models import build_models_yaml
from app.modules.semantic.registry import get_schema_version

router = APIRouter(prefix="/internal/cube", tags=["Internal — Cube"])


async def _check_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not settings.CUBE_INTERNAL_TOKEN:
        raise HTTPException(503, detail="CUBE_INTERNAL_TOKEN not configured")
    if x_internal_token != settings.CUBE_INTERNAL_TOKEN:
        raise HTTPException(401, detail="Invalid internal token")


@router.get("/schema-version", dependencies=[Depends(_check_internal_token)])
async def schema_version():
    return {"version": await get_schema_version()}


@router.get("/models", dependencies=[Depends(_check_internal_token)])
async def models(db: AsyncSession = Depends(get_db)):
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.status == DatasetStatus.READY,
            Dataset.is_deleted.is_(False),
            Dataset.marts_key.is_not(None),
        )
    )
    datasets = list(ds_result.scalars().all())

    bundles = []
    for ds in datasets:
        cols_result = await db.execute(
            select(DatasetColumn)
            .where(DatasetColumn.dataset_id == ds.id)
            .order_by(DatasetColumn.position)
        )
        metrics_result = await db.execute(
            select(SemanticMetric).where(SemanticMetric.dataset_id == ds.id)
        )
        bundles.append((ds, list(cols_result.scalars().all()), list(metrics_result.scalars().all())))

    content = build_models_yaml(bundles)
    return {"files": [{"fileName": "datasets.yml", "content": content}]}
