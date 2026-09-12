"""
app/modules/admin/audit.py — write admin action audit-log entries.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser, AuditLog

logger = structlog.get_logger()


async def write_audit(
    db: AsyncSession,
    admin: AdminUser,
    action: str,
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """
    Record an admin action. Best-effort — a logging failure must not break
    the underlying action, so the caller commits (this only adds the row).
    """
    try:
        ip = None
        if request is not None:
            ip = request.client.host if request.client else None
        db.add(AuditLog(
            admin_id=admin.id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details,
            ip_address=ip,
        ))
    except Exception as e:
        logger.warning("Audit log write failed", action=action, error=str(e))
