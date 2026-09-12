"""
app/core/scheduler.py
=====================
In-process APScheduler jobs. Safe ONLY with a single worker (the compose
backend runs --workers 1). Two jobs:
  - nightly_metrics_rollup: writes a SystemMetricSnapshot row for admin stats
  - report_schedule_tick:   generates any due scheduled reports
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from app.core.settings import settings

logger = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None


async def nightly_metrics_rollup() -> None:
    from app.db.models import (
        CopilotMessage, Dataset, Report, SystemMetricSnapshot, User,
    )
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        existing = await db.execute(
            select(SystemMetricSnapshot).where(SystemMetricSnapshot.snapshot_date == today)
        )
        snapshot = existing.scalar_one_or_none()
        if snapshot is None:
            snapshot = SystemMetricSnapshot(snapshot_date=today)
            db.add(snapshot)

        snapshot.total_users = (await db.execute(
            select(func.count()).select_from(User).where(User.is_deleted.is_(False))
        )).scalar() or 0
        snapshot.active_users = (await db.execute(
            select(func.count()).select_from(User).where(
                User.is_active.is_(True), User.is_deleted.is_(False)
            )
        )).scalar() or 0
        snapshot.total_datasets = (await db.execute(
            select(func.count()).select_from(Dataset).where(Dataset.is_deleted.is_(False))
        )).scalar() or 0
        snapshot.total_reports = (await db.execute(
            select(func.count()).select_from(Report).where(Report.is_deleted.is_(False))
        )).scalar() or 0
        snapshot.avg_query_latency_ms = (await db.execute(
            select(func.avg(CopilotMessage.latency_ms)).where(CopilotMessage.latency_ms.is_not(None))
        )).scalar()

        try:
            from app.modules.storage.object_store import get_minio
            client = get_minio()
            total = 0
            for bucket in (settings.MINIO_BUCKET_DATASETS, settings.MINIO_BUCKET_REPORTS):
                if client.bucket_exists(bucket):
                    total += sum(o.size or 0 for o in client.list_objects(bucket, recursive=True))
            snapshot.storage_bytes = total
        except Exception:
            pass

        await db.commit()
        logger.info("Metrics snapshot written", date=today.isoformat())


async def report_schedule_tick() -> None:
    from app.db.models import Report, ReportSchedule, ReportStatus
    from app.db.session import AsyncSessionLocal
    from app.modules.reports.router import generate_report_bg

    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as db:
        due = await db.execute(
            select(ReportSchedule).where(
                ReportSchedule.is_active.is_(True),
                (ReportSchedule.next_run_at.is_(None)) | (ReportSchedule.next_run_at <= now),
            )
        )
        for schedule in due.scalars().all():
            if schedule.hour_utc != now.hour and schedule.next_run_at is None:
                # first-time schedules only fire at their configured hour
                continue
            report = Report(
                owner_id=schedule.owner_id,
                dataset_id=schedule.dataset_id,
                name=f"{schedule.name} — {now.date().isoformat()}",
                status=ReportStatus.GENERATING,
            )
            db.add(report)
            await db.flush()
            report_id = str(report.id)

            schedule.last_run_at = now
            schedule.next_run_at = _next_run(now, schedule.cadence, schedule.hour_utc)
            await db.commit()

            import asyncio
            asyncio.create_task(generate_report_bg(report_id))
            logger.info("Scheduled report queued", schedule=schedule.name, report_id=report_id)


def _next_run(now: datetime, cadence: str, hour_utc: int):
    from datetime import timedelta
    days = 1 if cadence == "daily" else 7
    nxt = (now + timedelta(days=days)).replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    return nxt


def start_scheduler() -> None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED or _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(nightly_metrics_rollup, CronTrigger(hour=2, minute=0), id="metrics_rollup")
    _scheduler.add_job(report_schedule_tick, IntervalTrigger(minutes=15), id="report_tick")
    _scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
