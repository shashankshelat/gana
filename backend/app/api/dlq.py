import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.models.dlq import DLQEventModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/dlq", tags=["dlq"])


class BulkActionBody(BaseModel):
    ids: list[str]


# A DLQ row is never deleted: replaying it marks it resolved, discarding it keeps it as history.
DLQ_STATES = ("pending", "resolved", "discarded")


def _state_filter(state: str):
    if state == "pending":
        return DLQEventModel.discarded == False  # noqa: E712
    if state == "resolved":
        return (DLQEventModel.discarded == True) & (DLQEventModel.retry_count > 0)  # noqa: E712
    return (DLQEventModel.discarded == True) & (DLQEventModel.retry_count == 0)  # noqa: E712


def _state_of(e: DLQEventModel) -> str:
    if not e.discarded:
        return "pending"
    return "resolved" if (e.retry_count or 0) > 0 else "discarded"


@router.get("")
async def list_dlq(
    connector_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None, pattern="^(pending|resolved|discarded)$"),
    discarded: bool = Query(False),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cond = _state_filter(state) if state else DLQEventModel.discarded == discarded
    order = DLQEventModel.last_retry_at.desc() if state == "resolved" else DLQEventModel.created_at.desc()
    stmt = select(DLQEventModel).where(cond).order_by(order)
    if connector_id:
        stmt = stmt.where(DLQEventModel.connector_id == connector_id)

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    result = await db.execute(stmt.limit(limit).offset(offset))
    events = result.scalars().all()
    return {"items": [_to_dict(e) for e in events], "limit": limit, "offset": offset, "total": total}


async def _requeue(events: list[DLQEventModel]) -> tuple[int, int]:
    """Re-ingest DLQ events under their original connector so current mapping rules apply.

    Events that fail again land in the DLQ as new entries, so the retried ones are marked resolved."""
    from datetime import datetime
    from app.processors.pipeline import ingest_raw_events

    from app.models.connector import ConnectorModel

    # Events whose connector was deleted can never map again; leave them for discard instead of looping
    connector_ids = {e.connector_id for e in events if e.connector_id}
    async with AsyncSessionLocal() as db:
        existing = set((await db.execute(
            select(ConnectorModel.id).where(ConnectorModel.id.in_(connector_ids))
        )).scalars().all()) if connector_ids else set()

    by_connector: dict[tuple[str, str], list[DLQEventModel]] = {}
    for e in events:
        if e.discarded or e.connector_id not in existing:
            continue
        by_connector.setdefault((e.connector_id, e.connector_type or "unknown"), []).append(e)

    queued = failed = 0
    for (connector_id, connector_type), group in by_connector.items():
        # Stored events are the Kafka wrapper; re-ingest only the original vendor payload
        raws = [(e.raw_event or {}).get("_raw_data", e.raw_event) for e in group]
        s, f = await ingest_raw_events(connector_id=connector_id, connector_type=connector_type, raw_events=raws, dlq_retry=True)
        queued += s
        failed += f
        if f == 0:
            now = datetime.utcnow()
            for e in group:
                e.retry_count += 1
                e.last_retry_at = now
                e.discarded = True
    return queued, failed


@router.post("/{event_id}/retry")
async def retry_event(
    event_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    event = await _get_or_404(event_id, db)
    if event.retry_count >= event.max_retries:
        raise HTTPException(400, f"Max retries ({event.max_retries}) reached")
    from app.models.connector import ConnectorModel
    if not event.connector_id or not await db.get(ConnectorModel, event.connector_id):
        raise HTTPException(400, "This event's connector no longer exists, so it can't be re-mapped. Discard it instead.")
    queued, _ = await _requeue([event])
    return {"queued": queued, "retry_count": event.retry_count}


@router.post("/{event_id}/discard")
async def discard_event(
    event_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    event = await _get_or_404(event_id, db)
    event.discarded = True
    return _to_dict(event)


@router.post("/bulk/retry")
async def bulk_retry(
    body: BulkActionBody,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    events = (await db.execute(select(DLQEventModel).where(DLQEventModel.id.in_(body.ids)))).scalars().all()
    queued, failed = await _requeue(list(events))
    return {"success": queued, "failed": failed}


@router.post("/retry-all")
async def retry_all(
    connector_id: Optional[str] = Query(None),
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    """Retry every pending DLQ event (optionally for one connector), e.g. after fixing a mapping bug."""
    stmt = select(DLQEventModel).where(DLQEventModel.discarded == False)  # noqa: E712
    if connector_id:
        stmt = stmt.where(DLQEventModel.connector_id == connector_id)
    events = (await db.execute(stmt)).scalars().all()
    queued, failed = await _requeue(list(events))
    return {"pending": len(events), "queued": queued, "failed": failed}


@router.post("/ai-fix")
async def ai_fix_mapping(
    body: BulkActionBody,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    """Ask AI for a corrected mapping from selected DLQ events: one pending approval per connector."""
    from app.core.ai_autofix import SOURCE_MANUAL, ai_provider_config, propose
    from app.models.connector import ConnectorModel

    events = (await db.execute(select(DLQEventModel).where(
        DLQEventModel.id.in_(body.ids), DLQEventModel.discarded == False,  # noqa: E712
    ))).scalars().all()
    if not events:
        raise HTTPException(400, "No pending DLQ events selected")
    if not (await ai_provider_config())[2]:
        raise HTTPException(400, "No AI API key configured. Add one in Settings → AI Providers.")

    by_connector: dict[str, list[str]] = {}
    for e in events:
        if e.connector_id:
            by_connector.setdefault(e.connector_id, []).append(e.id)
    if not by_connector:
        raise HTTPException(400, "Selected events have no connector, so there is no mapping to fix")

    results = []
    for connector_id, ids in by_connector.items():
        connector = await db.get(ConnectorModel, connector_id)
        r = await propose(connector_id, source=SOURCE_MANUAL, created_by=current_user.username, dlq_ids=ids)
        results.append({
            "connector_id": connector_id, "connector_name": connector.name if connector else None,
            "approval_id": r.get("approval_id"), "events": len(ids),
            "rules_proposed": r.get("rules_proposed"), "error": None if r["status"] == "proposed" else r["message"],
        })
    return {"results": results}


@router.post("/bulk/discard")
async def bulk_discard(
    body: BulkActionBody,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    count = 0
    for eid in body.ids:
        result = await db.execute(select(DLQEventModel).where(DLQEventModel.id == eid))
        event = result.scalar_one_or_none()
        if event:
            event.discarded = True
            count += 1
    return {"discarded": count}


@router.get("/stats")
async def dlq_stats(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    counts = {st: await db.scalar(select(func.count()).select_from(DLQEventModel).where(_state_filter(st))) or 0
              for st in DLQ_STATES}

    from app.core.metrics import dlq_size
    dlq_size.set(counts["pending"])

    return counts


async def _get_or_404(event_id: str, db: AsyncSession) -> DLQEventModel:
    result = await db.execute(select(DLQEventModel).where(DLQEventModel.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "DLQ event not found")
    return event


def _to_dict(e: DLQEventModel) -> dict:
    return {
        "id": e.id,
        "connector_id": e.connector_id,
        "connector_type": e.connector_type,
        "connector_name": e.connector_name,
        "error_message": e.error_message,
        "error_type": e.error_type,
        "retry_count": e.retry_count,
        "max_retries": e.max_retries,
        "discarded": e.discarded,
        "state": _state_of(e),
        "raw_event": e.raw_event,
        "last_retry_at": e.last_retry_at.isoformat() if e.last_retry_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
