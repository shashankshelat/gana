from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ingestion_tracker import is_covered, paths_for_event, split_scope
from app.models.connector import ConnectorModel
from app.models.forwarder import ForwarderModel
from app.models.dlq import DLQEventModel
from app.models.ingestion import IngestionStatModel, UnmappedFieldModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.get("/summary")
async def ingestion_summary(
    days: int = Query(7, ge=1, le=90),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    rows = (await db.execute(
        select(IngestionStatModel).where(
            IngestionStatModel.day >= day_list[0],
            IngestionStatModel.kind.in_(["connector", "forwarder"]),
        )
    )).scalars().all()

    connectors = {c.id: c for c in (await db.execute(select(ConnectorModel))).scalars().all()}
    forwarders = {f.id: f for f in (await db.execute(select(ForwarderModel))).scalars().all()}

    daily = {d: {"day": d, "in_events": 0, "in_bytes": 0, "out_events": 0, "out_bytes": 0} for d in day_list}
    per_entity: dict[tuple[str, str], dict] = {}
    for r in rows:
        prefix = "in" if r.kind == "connector" else "out"
        if r.day in daily:
            daily[r.day][f"{prefix}_events"] += r.events
            daily[r.day][f"{prefix}_bytes"] += r.bytes
        e = per_entity.setdefault((r.kind, r.entity_id), {
            "events_today": 0, "bytes_today": 0, "events_period": 0, "bytes_period": 0,
        })
        e["events_period"] += r.events
        e["bytes_period"] += r.bytes
        if r.day == day_list[-1]:
            e["events_today"] += r.events
            e["bytes_today"] += r.bytes

    def _entities(kind: str, models: dict) -> list[dict]:
        ids = set(models) | {eid for (k, eid) in per_entity if k == kind}
        out = []
        for eid in ids:
            m = models.get(eid)
            stats = per_entity.get((kind, eid), {"events_today": 0, "bytes_today": 0, "events_period": 0, "bytes_period": 0})
            out.append({
                "id": eid,
                "name": m.name if m else "(deleted)",
                "type": (m.connector_type if kind == "connector" else m.forwarder_type) if m else None,
                **stats,
                "avg_event_bytes": stats["bytes_period"] // stats["events_period"] if stats["events_period"] else 0,
            })
        return sorted(out, key=lambda x: x["bytes_period"], reverse=True)

    connector_stats = _entities("connector", connectors)
    forwarder_stats = _entities("forwarder", forwarders)
    return {
        "days": days,
        "totals": {
            "in_events_today": sum(c["events_today"] for c in connector_stats),
            "in_bytes_today": sum(c["bytes_today"] for c in connector_stats),
            "in_events_period": sum(c["events_period"] for c in connector_stats),
            "in_bytes_period": sum(c["bytes_period"] for c in connector_stats),
            "out_events_today": sum(f["events_today"] for f in forwarder_stats),
            "out_bytes_today": sum(f["bytes_today"] for f in forwarder_stats),
            "out_events_period": sum(f["events_period"] for f in forwarder_stats),
            "out_bytes_period": sum(f["bytes_period"] for f in forwarder_stats),
        },
        "connectors": connector_stats,
        "forwarders": forwarder_stats,
        "daily": list(daily.values()),
    }


@router.get("/unmapped")
async def unmapped_samples(
    connector_id: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connectors = (await db.execute(select(ConnectorModel))).scalars().all()

    # Events examined for unmapped fields, so occurrences can be shown as a share of events
    scanned_rows = (await db.execute(
        select(IngestionStatModel.entity_id, func.sum(IngestionStatModel.events))
        .where(IngestionStatModel.kind == "unmapped_scan")
        .group_by(IngestionStatModel.entity_id)
    )).all()
    scanned = {eid: int(total or 0) for eid, total in scanned_rows}

    field_rows = (await db.execute(select(UnmappedFieldModel))).scalars().all()
    dlq_counts = dict((await db.execute(
        select(DLQEventModel.connector_id, func.count())
        .where(DLQEventModel.discarded == False)  # noqa: E712
        .group_by(DLQEventModel.connector_id)
    )).all())

    def still_unmapped(f: UnmappedFieldModel, rules: dict) -> bool:
        # Check against the rules of the route the field was seen under, so fixes drop it off the list
        scope, path = split_scope(f.field_path)
        route = next((r for r in rules.get("_routes") or [] if r.get("name") == scope), None) if scope else None
        return not is_covered(path, paths_for_event(rules, route))

    summary = []
    rules_by_connector = {}
    for c in connectors:
        rules_by_connector[c.id] = c.mapping_rules or {}
        open_fields = [f for f in field_rows if f.connector_id == c.id and still_unmapped(f, c.mapping_rules or {})]
        summary.append({
            "id": c.id,
            "name": c.name,
            "connector_type": c.connector_type,
            "mapping_rule_count": len(c.mapping_rules or {}),
            "events_scanned": scanned.get(c.id, 0),
            "unmapped_field_count": len(open_fields),
            "unmapped_event_count": dlq_counts.get(c.id, 0),
        })

    result = {"connectors": summary, "fields": [], "unmapped_events": []}
    if not connector_id:
        return result

    rules = rules_by_connector.get(connector_id, {})
    total = scanned.get(connector_id, 0)
    fields = [f for f in field_rows if f.connector_id == connector_id and still_unmapped(f, rules)]
    result["fields"] = [
        {
            "id": f.id,
            "field_path": f.field_path,
            "occurrences": f.occurrences,
            "coverage_pct": round(min(100.0, 100.0 * f.occurrences / total), 1) if total else None,
            "sample_values": f.sample_values or [],
            "first_seen": f.first_seen.isoformat() if f.first_seen else None,
            "last_seen": f.last_seen.isoformat() if f.last_seen else None,
        }
        for f in sorted(fields, key=lambda f: f.occurrences, reverse=True)
    ]

    dlq = (await db.execute(
        select(DLQEventModel)
        .where(DLQEventModel.connector_id == connector_id, DLQEventModel.discarded == False)  # noqa: E712
        .order_by(DLQEventModel.created_at.desc())
        .limit(20)
    )).scalars().all()
    result["unmapped_events"] = [
        {
            "id": d.id,
            "error_type": d.error_type,
            "error_message": d.error_message,
            "raw_event": (d.raw_event or {}).get("_raw_data", d.raw_event),
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in dlq
    ]
    return result


@router.get("/unmapped/sample-event")
async def unmapped_sample_event(
    field_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(UnmappedFieldModel, field_id)
    if not row:
        raise HTTPException(404, "Field not found")
    return {"field_path": row.field_path, "sample_event": row.sample_event}


@router.delete("/unmapped/{connector_id}", status_code=204)
async def reset_unmapped(
    connector_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(UnmappedFieldModel).where(UnmappedFieldModel.connector_id == connector_id))
    await db.execute(delete(IngestionStatModel).where(
        IngestionStatModel.kind == "unmapped_scan", IngestionStatModel.entity_id == connector_id,
    ))
