"""
app/modules/admin/settings/router.py — Platform configuration (admin only).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.common.schemas import success
from app.core.settings import settings
from app.db.models import AdminUser
from app.modules.auth.dependencies import get_current_admin

router = APIRouter(prefix="/admin/settings", tags=["Admin — Settings"])


@router.get("/")
async def get_settings(admin: AdminUser = Depends(get_current_admin)):
    return success({
        "app_name": settings.APP_NAME,
        "app_env": settings.APP_ENV,
        "debug": settings.DEBUG,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "max_query_rows": settings.MAX_QUERY_ROWS,
        "ai_provider": "groq",
        "groq_model_pool": settings.groq_model_pool,
        "semantic_engine": settings.SEMANTIC_ENGINE,
        "dbt_enabled": settings.DBT_ENABLED,
        "scheduler_enabled": settings.SCHEDULER_ENABLED,
        "duckdb_memory_limit": settings.DUCKDB_MEMORY_LIMIT,
    })
