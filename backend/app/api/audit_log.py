import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLogModel
from app.models.user import UserModel
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("")
async def list_audit_log(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    filters = []
    if username:
        filters.append(AuditLogModel.username == username)
    if action:
        filters.append(AuditLogModel.action.contains(action))
    if resource_type:
        filters.append(AuditLogModel.resource_type == resource_type)
    if filters:
        stmt = stmt.where(and_(*filters))

    count_stmt = stmt.with_only_columns(AuditLogModel.id)
    result = await db.execute(stmt.limit(limit).offset(offset))
    entries = result.scalars().all()
    return {
        "items": [_to_dict(e) for e in entries],
        "limit": limit,
        "offset": offset,
    }


@router.get("/export")
async def export_csv(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(10000)
    )
    entries = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["created_at", "username", "action", "resource_type", "resource_name", "status", "ip_address"])
    writer.writeheader()
    for e in entries:
        writer.writerow({
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "username": e.username or "",
            "action": e.action,
            "resource_type": e.resource_type or "",
            "resource_name": e.resource_name or "",
            "status": e.status,
            "ip_address": e.ip_address or "",
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )


def _to_dict(e: AuditLogModel) -> dict:
    return {
        "id": e.id,
        "username": e.username,
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "resource_name": e.resource_name,
        "detail": e.detail,
        "ip_address": e.ip_address,
        "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
