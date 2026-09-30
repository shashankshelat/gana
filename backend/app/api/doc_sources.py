from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.doc_watcher import run_doc_watcher
from app.models.doc_source import ConnectorDocSourceModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/doc-sources", tags=["doc-sources"])


@router.get("")
async def list_doc_sources(
    connector_type: str | None = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ConnectorDocSourceModel).order_by(
        ConnectorDocSourceModel.connector_type,
        ConnectorDocSourceModel.created_at,
    )
    if connector_type:
        stmt = stmt.where(ConnectorDocSourceModel.connector_type == connector_type)
    result = await db.execute(stmt)
    return [_to_dict(s) for s in result.scalars().all()]


@router.post("/check-now")
async def trigger_doc_check(
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(require_role("admin")),
):
    """Manually trigger a full documentation check cycle."""
    background_tasks.add_task(run_doc_watcher)
    return {"status": "doc check started in background"}


@router.patch("/{source_id}/toggle")
async def toggle_doc_source(
    source_id: str,
    current_user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(ConnectorDocSourceModel, source_id)
    if not source:
        from fastapi import HTTPException
        raise HTTPException(404, "Doc source not found")
    source.enabled = not source.enabled
    return _to_dict(source)


def _to_dict(s: ConnectorDocSourceModel) -> dict:
    return {
        "id": s.id,
        "connector_type": s.connector_type,
        "url": s.url,
        "description": s.description,
        "enabled": s.enabled,
        "content_hash": s.content_hash,
        "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
        "last_changed_at": s.last_changed_at.isoformat() if s.last_changed_at else None,
    }
