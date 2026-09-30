from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.anomaly import AnomalyModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
async def list_anomalies(
    connector_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, le=500),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnomalyModel).order_by(AnomalyModel.created_at.desc())
    if connector_id:
        stmt = stmt.where(AnomalyModel.connector_id == connector_id)
    if severity:
        stmt = stmt.where(AnomalyModel.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(AnomalyModel.acknowledged == (1 if acknowledged else 0))
    result = await db.execute(stmt.limit(limit))
    return [_to_dict(a) for a in result.scalars().all()]


@router.post("/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(
    anomaly_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnomalyModel).where(AnomalyModel.id == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        from fastapi import HTTPException
        raise HTTPException(404, "Anomaly not found")
    anomaly.acknowledged = 1
    anomaly.acknowledged_by = current_user.username
    return _to_dict(anomaly)


@router.get("/stats")
async def anomaly_stats(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    total = await db.scalar(select(func.count()).select_from(AnomalyModel))
    unacked = await db.scalar(select(func.count()).select_from(AnomalyModel).where(AnomalyModel.acknowledged == 0))
    critical = await db.scalar(select(func.count()).select_from(AnomalyModel).where(
        AnomalyModel.severity == "critical", AnomalyModel.acknowledged == 0
    ))
    return {"total": total or 0, "unacknowledged": unacked or 0, "critical_unacknowledged": critical or 0}


def _to_dict(a: AnomalyModel) -> dict:
    return {
        "id": a.id,
        "connector_id": a.connector_id,
        "connector_type": a.connector_type,
        "anomaly_type": a.anomaly_type,
        "severity": a.severity,
        "title": a.title,
        "description": a.description,
        "baseline_value": a.baseline_value,
        "observed_value": a.observed_value,
        "z_score": a.z_score,
        "acknowledged": bool(a.acknowledged),
        "acknowledged_by": a.acknowledged_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
