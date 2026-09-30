import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cron_job import CronJobModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/cron", tags=["cron"])

_scheduler_ref = None


def set_scheduler(scheduler):
    global _scheduler_ref
    _scheduler_ref = scheduler


class CronJobCreate(BaseModel):
    connector_id: str
    cron_expression: str
    description: Optional[str] = None
    enabled: bool = True


class CronJobUpdate(BaseModel):
    cron_expression: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


def _validate_cron(expr: str) -> bool:
    parts = expr.strip().split()
    return len(parts) in (5, 6)


@router.get("")
async def list_cron_jobs(
    connector_id: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CronJobModel).order_by(CronJobModel.created_at.desc())
    if connector_id:
        stmt = stmt.where(CronJobModel.connector_id == connector_id)
    result = await db.execute(stmt)
    return [_to_dict(j) for j in result.scalars().all()]


@router.post("", status_code=201)
async def create_cron_job(
    body: CronJobCreate,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    if not _validate_cron(body.cron_expression):
        raise HTTPException(400, "Invalid cron expression (needs 5 or 6 space-separated fields)")

    from app.models.connector import ConnectorModel
    conn_result = await db.execute(select(ConnectorModel).where(ConnectorModel.id == body.connector_id))
    connector = conn_result.scalar_one_or_none()
    if not connector:
        raise HTTPException(404, "Connector not found")

    job = CronJobModel(
        id=str(uuid.uuid4()),
        connector_id=body.connector_id,
        connector_name=connector.name,
        cron_expression=body.cron_expression,
        description=body.description,
        enabled=body.enabled,
        created_by=current_user.username,
    )
    db.add(job)
    await db.flush()

    if body.enabled and _scheduler_ref:
        _register_job(job)

    return _to_dict(job)


@router.patch("/{job_id}")
async def update_cron_job(
    job_id: str,
    body: CronJobUpdate,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_or_404(job_id, db)
    if body.cron_expression:
        if not _validate_cron(body.cron_expression):
            raise HTTPException(400, "Invalid cron expression")
        job.cron_expression = body.cron_expression
    if body.description is not None:
        job.description = body.description
    if body.enabled is not None:
        job.enabled = body.enabled
        if _scheduler_ref:
            try:
                _scheduler_ref.remove_job(f"cron_{job_id}")
            except Exception:
                pass
            if body.enabled:
                _register_job(job)

    return _to_dict(job)


@router.delete("/{job_id}", status_code=204)
async def delete_cron_job(
    job_id: str,
    current_user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_or_404(job_id, db)
    if _scheduler_ref:
        try:
            _scheduler_ref.remove_job(f"cron_{job_id}")
        except Exception:
            pass
    await db.delete(job)


@router.post("/{job_id}/run")
async def run_now(
    job_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_or_404(job_id, db)
    result = await _execute_cron_job(job.connector_id, job_id)
    return result


def _register_job(job: CronJobModel):
    if not _scheduler_ref:
        return
    parts = job.cron_expression.strip().split()
    cron_kwargs = {}
    fields = ["minute", "hour", "day", "month", "day_of_week"]
    for i, field in enumerate(fields):
        if i < len(parts):
            cron_kwargs[field] = parts[i]

    _scheduler_ref.add_job(
        _execute_cron_job,
        "cron",
        id=f"cron_{job.id}",
        args=[job.connector_id, job.id],
        replace_existing=True,
        **cron_kwargs,
    )


async def _execute_cron_job(connector_id: str, job_id: str) -> dict:
    from datetime import datetime
    from app.core.database import AsyncSessionLocal
    from app.core.poller import poll_connector

    # Shares the automatic poller's checkpoint, so cron runs never re-ingest events already sent
    result = await poll_connector(connector_id)

    async with AsyncSessionLocal() as db:
        job = await db.get(CronJobModel, job_id)
        if job:
            job.last_run_at = datetime.utcnow()
            job.last_events_fetched = result.get("new_events", 0)
            if "error" in result:
                job.last_result, job.last_error = "error", str(result["error"])[:500]
            elif "skipped" in result:
                job.last_result, job.last_error = "skipped", result["skipped"]
            else:
                job.last_result = "success" if result.get("failed", 0) == 0 else "partial"
                job.last_error = None
            await db.commit()
    return result


async def load_cron_jobs(scheduler):
    set_scheduler(scheduler)
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CronJobModel).where(CronJobModel.enabled == True))
        jobs = result.scalars().all()
    for job in jobs:
        try:
            _register_job(job)
        except Exception as e:
            pass


async def _get_or_404(job_id: str, db: AsyncSession) -> CronJobModel:
    result = await db.execute(select(CronJobModel).where(CronJobModel.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Cron job not found")
    return job


def _to_dict(j: CronJobModel) -> dict:
    return {
        "id": j.id,
        "connector_id": j.connector_id,
        "connector_name": j.connector_name,
        "cron_expression": j.cron_expression,
        "description": j.description,
        "enabled": j.enabled,
        "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
        "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
        "last_events_fetched": j.last_events_fetched,
        "last_result": j.last_result,
        "last_error": j.last_error,
        "created_by": j.created_by,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }
