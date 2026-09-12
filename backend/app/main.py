"""
app/main.py — FastAPI application factory.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.logging import configure_logging
from app.core.settings import settings

configure_logging(settings.LOG_LEVEL)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("InsightAI API starting", env=settings.APP_ENV)

    try:
        from app.core.redis import get_redis
        await get_redis().ping()
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning("Redis unavailable", error=str(exc))

    try:
        from app.modules.datasets.service import get_duckdb
        get_duckdb().execute("SELECT 1")
        logger.info("DuckDB ready")
    except Exception as exc:
        logger.warning("DuckDB unavailable", error=str(exc))

    try:
        from app.modules.storage.object_store import ensure_bucket
        ensure_bucket(settings.MINIO_BUCKET_DATASETS)
        ensure_bucket(settings.MINIO_BUCKET_REPORTS)
        logger.info("MinIO buckets ready")
    except Exception as exc:
        logger.warning("MinIO unavailable", error=str(exc))

    try:
        from app.core.scheduler import start_scheduler
        start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler failed to start", error=str(exc))

    yield
    logger.info("InsightAI API shutting down")
    from app.core.scheduler import stop_scheduler
    stop_scheduler()
    from app.core.redis import close_redis
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="InsightAI API",
        description="AI-powered Meta Ads Intelligence Platform — FastAPI backend.",
        version="1.0.0",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{ms}ms"
        logger.debug("request", method=request.method, path=request.url.path,
                     status=response.status_code, duration_ms=ms)
        return response

    @app.exception_handler(404)
    async def not_found(_req, _exc):
        return JSONResponse(
            content={"success": False, "error": {"code": "NOT_FOUND", "message": "Resource not found."}},
            status_code=404,
        )

    @app.exception_handler(500)
    async def internal_error(_req, exc):
        logger.error("Unhandled error", error=str(exc))
        return JSONResponse(
            content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error."}},
            status_code=500,
        )

    p = settings.API_V1_PREFIX

    from app.modules.auth.router import router as auth_router
    from app.modules.auth.me_router import router as me_router
    from app.modules.users.router import router as users_router
    from app.modules.datasets.router import router as datasets_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.insights.router import router as insights_router
    from app.modules.copilot.router import router as copilot_router
    from app.modules.dashboards.router import router as dashboards_router
    from app.modules.reports.router import router as reports_router
    from app.modules.semantic.router import router as semantic_router
    from app.modules.semantic.internal_router import router as semantic_internal_router
    from app.modules.admin.users.router import router as admin_users_router
    from app.modules.admin.monitoring.router import router as admin_monitoring_router
    from app.modules.admin.settings.router import router as admin_settings_router
    from app.modules.admin.analytics.router import router as admin_analytics_router

    for router in [
        auth_router, me_router, users_router, datasets_router,
        analytics_router, insights_router, copilot_router,
        dashboards_router, reports_router,
        semantic_router, semantic_internal_router,
        admin_users_router, admin_monitoring_router, admin_settings_router,
        admin_analytics_router,
    ]:
        app.include_router(router, prefix=p)

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "service": "insightai-api", "version": "1.0.0"}

    return app


app = create_app()
