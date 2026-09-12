"""
app/modules/admin/monitoring/router.py — System health and metrics.
"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.db.models import AdminUser
from app.db.session import get_db, engine
from app.modules.auth.dependencies import get_current_admin

router = APIRouter(prefix="/admin/monitoring", tags=["Admin — Monitoring"])


@router.get("/health")
async def system_health(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    checks = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    try:
        from app.core.redis import get_redis
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    try:
        from app.modules.datasets.service import get_duckdb
        get_duckdb().execute("SELECT 1").fetchone()
        checks["duckdb"] = "ok"
    except Exception as e:
        checks["duckdb"] = f"error: {e}"

    try:
        from app.modules.storage.object_store import get_minio
        get_minio().bucket_exists("test-ping")
        checks["minio"] = "ok"
    except Exception as e:
        checks["minio"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return success({"status": "ok" if all_ok else "degraded", "checks": checks})


@router.get("/stats")
async def system_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.db.models import SystemMetricSnapshot

    pool = engine.pool

    snap_result = await db.execute(
        select(SystemMetricSnapshot).order_by(SystemMetricSnapshot.snapshot_date.desc()).limit(30)
    )
    snapshots = list(snap_result.scalars().all())
    trend = [
        {
            "date": s.snapshot_date.date().isoformat(),
            "total_users": s.total_users,
            "active_users": s.active_users,
            "total_datasets": s.total_datasets,
            "total_reports": s.total_reports,
            "avg_query_latency_ms": s.avg_query_latency_ms,
            "storage_bytes": s.storage_bytes,
        }
        for s in reversed(snapshots)
    ]

    return success({
        "db_pool_size": pool.size(),
        "db_checked_out": pool.checkedout(),
        "db_overflow": pool.overflow(),
        "process_memory_mb": round(
            int(open("/proc/self/status").read().split("VmRSS:")[1].split("kB")[0].strip()) / 1024, 1
        ) if os.path.exists("/proc/self/status") else None,
        "latest_snapshot": trend[-1] if trend else None,
        "snapshots": trend,
    })


@router.get("/audit-logs")
async def audit_logs(
    page: int = 1,
    per_page: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.db.models import AuditLog
    offset = (page - 1) * per_page
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(offset).limit(per_page)
    )
    return success({
        "logs": [
            {
                "id": str(log.id),
                "admin_id": str(log.admin_id) if log.admin_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in result.scalars().all()
        ]
    })
