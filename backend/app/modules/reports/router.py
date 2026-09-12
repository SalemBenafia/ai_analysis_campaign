"""
app/modules/reports/router.py — Report generation, download, schedules.

PDFs are built from the dataset's KPIs, discovery findings and the user's
pinned insights. Presigned URLs are always regenerated on download (never
persisted, so they can't silently expire).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import success
from app.core.settings import settings
from app.db.models import (
    Dataset, DatasetColumn, DatasetStatus, Report, ReportSchedule, ReportStatus,
    SavedInsight, User,
)
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user

router = APIRouter(prefix="/reports", tags=["Reports"])

logger = structlog.get_logger()


class CreateReportRequest(BaseModel):
    dataset_id: uuid.UUID
    name: str
    description: str | None = None


async def generate_report_bg(report_id: str) -> None:
    """Build the PDF for a report row and upload it to MinIO."""
    from app.db.session import AsyncSessionLocal
    from app.modules.analytics.engine import compute_kpis, group_by_metric
    from app.modules.insights.engine import run_full_discovery
    from app.modules.reports.generator import generate_report_pdf
    from app.modules.storage.object_store import upload_bytes

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if not report:
            return

        ds_result = await db.execute(select(Dataset).where(Dataset.id == report.dataset_id))
        ds = ds_result.scalar_one_or_none()
        if not ds:
            report.status = ReportStatus.ERROR
            await db.commit()
            return

        try:
            cols_result = await db.execute(
                select(DatasetColumn).where(DatasetColumn.dataset_id == report.dataset_id)
            )
            cols = cols_result.scalars().all()
            metric_cols = [c.name for c in cols if c.is_metric]
            dim_cols = [c.name for c in cols if c.is_dimension]
            date_cols = [c.name for c in cols if c.col_type.value in ("date", "datetime")]
            allowed = {c.name for c in cols}

            kpis = compute_kpis(ds.duckdb_table, metric_cols, allowed) if metric_cols else {}
            top = (
                group_by_metric(ds.duckdb_table, dim_cols[0], metric_cols[0], allowed)
                if metric_cols and dim_cols else []
            )
            findings = run_full_discovery(
                ds.duckdb_table, metric_cols, dim_cols, allowed,
                date_cols[0] if date_cols else None,
            )

            insights = _findings_to_text(ds, findings)

            # Include the user's pinned saved insights (name + AI narrative).
            pinned_result = await db.execute(
                select(SavedInsight).where(
                    SavedInsight.owner_id == report.owner_id,
                    SavedInsight.is_pinned.is_(True),
                    SavedInsight.is_deleted.is_(False),
                ).limit(5)
            )
            for ins in pinned_result.scalars().all():
                text = f"Pinned insight '{ins.name}'"
                if ins.ai_explanation:
                    text += f": {ins.ai_explanation}"
                insights.append(text)

            pdf_bytes = generate_report_pdf(
                report_name=report.name,
                dataset_name=ds.name,
                kpis={k.replace("_sum", ""): v for k, v in kpis.items() if "_sum" in k},
                top_performers=top[:10],
                insights=insights,
                generated_at=datetime.now(tz=timezone.utc),
            )

            key = f"reports/{report_id}/{report.name.replace(' ', '_')}.pdf"
            upload_bytes(settings.MINIO_BUCKET_REPORTS, key, pdf_bytes, "application/pdf")

            report.minio_key = key
            report.download_url = None  # never persist presigned URLs
            report.status = ReportStatus.READY
            report.generated_at = datetime.now(tz=timezone.utc)
        except Exception as e:
            report.status = ReportStatus.ERROR
            logger.error("Report generation failed", report_id=report_id, error=str(e))

        await db.commit()


def _findings_to_text(ds: Dataset, findings: dict) -> list[str]:
    lines: list[str] = []
    if ds.row_count:
        lines.append(f"Dataset contains {ds.row_count:,} rows and {ds.column_count} columns.")

    top = findings.get("top_performers") or []
    if top:
        best = top[0]
        label = next((v for k, v in best.items() if k not in ("rank", "value")), "top item")
        lines.append(f"Top performer: {label} with value {best.get('value', 0):,.2f}.")

    trend = findings.get("trend") or {}
    if trend.get("trend") in ("up", "down"):
        lines.append(
            f"Primary metric trend is {trend['trend']} ({trend.get('pct_change', 0):+.1f}% over the period)."
        )

    anomalies = findings.get("anomalies") or []
    if anomalies:
        lines.append(f"Detected {len(anomalies)} anomalous data point(s) worth reviewing.")

    corr = findings.get("correlation") or {}
    if corr.get("label") and corr["label"] not in ("weak", "unknown"):
        lines.append(
            f"{corr['metric_a']} and {corr['metric_b']} show a {corr['label'].replace('_', ' ')} correlation."
        )
    return lines


@router.post("/")
async def create_report(
    payload: CreateReportRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == payload.dataset_id,
            Dataset.owner_id == user.id,
            Dataset.status == DatasetStatus.READY,
        )
    )
    if not ds_result.scalar_one_or_none():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    report = Report(
        owner_id=user.id,
        dataset_id=payload.dataset_id,
        name=payload.name,
        description=payload.description,
        status=ReportStatus.GENERATING,
    )
    db.add(report)
    await db.commit()

    background_tasks.add_task(generate_report_bg, str(report.id))
    return success({"report_id": str(report.id), "status": "generating"}, "Report generation started.")


@router.get("/")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report).where(
            Report.owner_id == user.id,
            Report.is_deleted.is_(False),
        ).order_by(Report.created_at.desc())
    )
    return success({
        "reports": [
            {
                "id": str(r.id),
                "name": r.name,
                "status": r.status.value,
                "has_download": bool(r.minio_key),
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in result.scalars().all()
        ]
    })


async def _get_ready_report(report_id: uuid.UUID, user: User, db: AsyncSession) -> Report:
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.owner_id == user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Report not found."})
    if report.status != ReportStatus.READY or not report.minio_key:
        raise HTTPException(400, detail={"code": "NOT_READY", "message": "Report not ready yet."})
    return report


@router.get("/{report_id}/download")
async def get_download_url(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the API path serving the PDF. A MinIO presigned URL is useless
    here: it carries the backend's INTERNAL endpoint (minio:9000 inside
    Docker), which the user's browser cannot reach — the file therefore
    streams through the API instead.
    """
    await _get_ready_report(report_id, user, db)
    return success({"download_url": f"{settings.API_V1_PREFIX}/reports/{report_id}/file"})


@router.get("/{report_id}/file")
async def download_file(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the report PDF from MinIO through the API (auth included)."""
    report = await _get_ready_report(report_id, user, db)
    from app.modules.storage.object_store import download_bytes

    try:
        pdf = download_bytes(settings.MINIO_BUCKET_REPORTS, report.minio_key)
    except Exception as e:
        logger.error("Report file fetch failed", report_id=str(report_id), error=str(e))
        raise HTTPException(502, detail={"code": "STORAGE_ERROR", "message": "Could not fetch the report file."})

    filename = report.minio_key.rsplit("/", 1)[-1] or "report.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{report_id}")
async def delete_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.owner_id == user.id, Report.is_deleted.is_(False))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Report not found."})
    report.is_deleted = True
    report.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return success({}, "Report deleted.")


# ─── Scheduled reports ────────────────────────────────────────────────────────


class CreateScheduleRequest(BaseModel):
    dataset_id: uuid.UUID
    name: str
    cadence: str = "weekly"   # daily | weekly
    hour_utc: int = 6


def _schedule_row(s: ReportSchedule) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "dataset_id": str(s.dataset_id),
        "cadence": s.cadence,
        "hour_utc": s.hour_utc,
        "is_active": s.is_active,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
    }


@router.post("/schedules")
async def create_schedule(
    payload: CreateScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.cadence not in ("daily", "weekly"):
        raise HTTPException(400, detail={"code": "INVALID_CADENCE", "message": "cadence must be daily or weekly."})
    ds_result = await db.execute(
        select(Dataset).where(
            Dataset.id == payload.dataset_id, Dataset.owner_id == user.id,
            Dataset.is_deleted.is_(False),
        )
    )
    if not ds_result.scalar_one_or_none():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Dataset not found."})

    schedule = ReportSchedule(
        owner_id=user.id,
        dataset_id=payload.dataset_id,
        name=payload.name,
        cadence=payload.cadence,
        hour_utc=max(0, min(payload.hour_utc, 23)),
    )
    db.add(schedule)
    await db.commit()
    return success(_schedule_row(schedule), "Schedule created.")


@router.get("/schedules")
async def list_schedules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportSchedule).where(ReportSchedule.owner_id == user.id)
        .order_by(ReportSchedule.created_at.desc())
    )
    return success({"schedules": [_schedule_row(s) for s in result.scalars().all()]})


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    cadence: str | None = None
    hour_utc: int | None = None
    is_active: bool | None = None


@router.patch("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: uuid.UUID,
    payload: UpdateScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id, ReportSchedule.owner_id == user.id
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Schedule not found."})
    if payload.name is not None:
        schedule.name = payload.name
    if payload.cadence in ("daily", "weekly"):
        schedule.cadence = payload.cadence
    if payload.hour_utc is not None:
        schedule.hour_utc = max(0, min(payload.hour_utc, 23))
    if payload.is_active is not None:
        schedule.is_active = payload.is_active
    await db.commit()
    return success(_schedule_row(schedule), "Schedule updated.")


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id, ReportSchedule.owner_id == user.id
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Schedule not found."})
    await db.delete(schedule)
    await db.commit()
    return success({}, "Schedule deleted.")
