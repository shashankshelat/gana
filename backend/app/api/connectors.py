import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mapping_cache import mapping_cache
from app.models.connector import ConnectorModel
from app.connectors.registry import list_connector_types, instantiate_connector, get_connector_class
from app.processors.pipeline import ingest_raw_events
from app.core.poller import poll_connector, has_enabled_forwarder

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorCreate(BaseModel):
    name: str
    connector_type: str
    description: Optional[str] = None
    enabled: bool = True
    config: dict = {}
    mapping_rules: dict = {}
    # Normally omitted: the class comes from the connector type and, per event, from the mapping's routes
    ocsf_class_uid: Optional[int] = None


class ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    mapping_rules: Optional[dict] = None
    ocsf_class_uid: Optional[int] = None


@router.get("/types")
async def get_connector_types():
    return list_connector_types()


@router.get("")
async def list_connectors(
    enabled: Optional[bool] = None,
    connector_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ConnectorModel)
    if enabled is not None:
        stmt = stmt.where(ConnectorModel.enabled == enabled)
    if connector_type:
        stmt = stmt.where(ConnectorModel.connector_type == connector_type)
    result = await db.execute(stmt)
    connectors = result.scalars().all()
    states = await _poll_states(db, [c.id for c in connectors])
    return [{**_connector_to_dict(c), **_health(c, states.get(c.id))} for c in connectors]


@router.post("", status_code=201)
async def create_connector(body: ConnectorCreate, db: AsyncSession = Depends(get_db)):
    cls = get_connector_class(body.connector_type)
    if not cls:
        raise HTTPException(400, f"Unknown connector type: {body.connector_type}")
    if not await has_enabled_forwarder(db):
        raise HTTPException(409, "Configure and enable at least one forwarder before adding a connector")

    connector_id = str(uuid.uuid4())
    mapping = body.mapping_rules or cls.meta.default_mapping
    class_uid = cls.meta.default_ocsf_class_uid if body.ocsf_class_uid is None else body.ocsf_class_uid

    connector = ConnectorModel(
        id=connector_id,
        name=body.name,
        connector_type=body.connector_type,
        description=body.description,
        enabled=body.enabled,
        config=body.config,
        mapping_rules=mapping,
        ocsf_class_uid=class_uid,
    )
    db.add(connector)
    await db.flush()
    mapping_cache.update(connector_id, mapping, class_uid)
    return _connector_to_dict(connector)


@router.get("/{connector_id}")
async def get_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    connector = await _get_or_404(connector_id, db)
    states = await _poll_states(db, [connector.id])
    return {**_connector_to_dict(connector), **_health(connector, states.get(connector.id))}


@router.patch("/{connector_id}")
async def update_connector(connector_id: str, body: ConnectorUpdate, db: AsyncSession = Depends(get_db)):
    connector = await _get_or_404(connector_id, db)
    updates = body.model_dump(exclude_none=True)
    if "config" in updates:
        # The UI receives secrets masked as "***"; don't let a round-trip overwrite the stored value
        existing = connector.config or {}
        updates["config"] = {
            k: existing.get(k, v) if v == "***" else v
            for k, v in updates["config"].items()
        }
    for key, value in updates.items():
        setattr(connector, key, value)
    connector.updated_at = datetime.utcnow()
    mapping_cache.update(connector_id, connector.mapping_rules or {},
                         3002 if connector.ocsf_class_uid is None else connector.ocsf_class_uid)
    return _connector_to_dict(connector)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    connector = await _get_or_404(connector_id, db)
    await db.delete(connector)
    mapping_cache.invalidate(connector_id)


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    connector = await _get_or_404(connector_id, db)
    instance = instantiate_connector(
        connector.connector_type, connector_id, connector.config, connector.mapping_rules
    )
    if not instance:
        raise HTTPException(400, "Cannot instantiate connector")
    success, message = await instance.test_connection()
    return {"success": success, "message": message}


@router.post("/{connector_id}/poll")
async def poll_connector_now(connector_id: str):
    # No request-scoped session here: poll_connector writes in its own, and SQLite would lock against ours
    result = await poll_connector(connector_id)
    if "error" in result:
        raise HTTPException(502, result["error"])
    if "skipped" in result:
        raise HTTPException(409, result["skipped"])
    return result


@router.post("/webhooks/{connector_type}/{connector_id}")
async def receive_webhook(
    connector_type: str,
    connector_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    connector = await _get_or_404(connector_id, db)
    if not connector.enabled:
        raise HTTPException(400, "Connector is disabled")
    if not await has_enabled_forwarder(db):
        raise HTTPException(503, "No enabled forwarder configured")

    raw_body = await request.body()
    headers = dict(request.headers)

    instance = instantiate_connector(
        connector.connector_type, connector_id, connector.config, connector.mapping_rules
    )
    if not instance:
        raise HTTPException(400, "Cannot instantiate connector")

    # Connectors that sign their webhooks (e.g. Slack) must pass verification before anything is ingested
    if hasattr(instance, "verify_webhook_signature") and not instance.verify_webhook_signature(raw_body, headers):
        raise HTTPException(401, "Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(400, "Body is not valid JSON")

    # Slack verifies a Request URL by expecting its challenge value echoed back
    if isinstance(payload, dict) and payload.get("type") == "url_verification" and "challenge" in payload:
        return {"challenge": payload["challenge"]}

    events = await instance.handle_webhook(payload, headers)
    success, failed = await ingest_raw_events(
        connector_id=connector_id,
        connector_type=connector.connector_type,
        raw_events=events,
    )

    connector.events_processed += success
    connector.last_event_at = datetime.utcnow()

    return {"ok": True, "events_received": len(events), "queued": success}


async def _get_or_404(connector_id: str, db: AsyncSession) -> ConnectorModel:
    result = await db.execute(select(ConnectorModel).where(ConnectorModel.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(404, "Connector not found")
    return connector


async def _poll_states(db: AsyncSession, ids: list[str]) -> dict:
    from app.models.poll_state import ConnectorPollStateModel
    if not ids:
        return {}
    rows = (await db.execute(select(ConnectorPollStateModel).where(ConnectorPollStateModel.connector_id.in_(ids)))).scalars()
    return {r.connector_id: r for r in rows}


_RECEIVING_WINDOW = timedelta(hours=24)


def _health(c: ConnectorModel, state) -> dict:
    """One status for the connectors table: disabled, error, attention, receiving, idle or waiting."""
    cls = get_connector_class(c.connector_type)
    webhook = bool(cls and cls.meta.supports_webhook)
    info = {
        "last_polled_at": state.last_polled_at.isoformat() if state and state.last_polled_at else None,
        "poll_status": state.last_status if state else None,
        "poll_error": state.last_error if state else None,
    }
    recent = c.last_event_at and datetime.utcnow() - c.last_event_at < _RECEIVING_WINDOW
    if not c.enabled:
        health, detail = "disabled", "Disabled"
    elif state and state.last_status == "error":
        health, detail = "error", state.last_error or "Last poll failed"
    elif recent:
        health, detail = "receiving", "Events in the last 24 hours"
    elif state and state.last_status == "skipped" and not webhook:
        # Push-capable connectors skip polling by design; only pull-only ones need setup
        health, detail = "attention", state.last_error or "Polling is not configured"
    elif c.last_event_at:
        health, detail = "idle", "No events in the last 24 hours"
    else:
        health, detail = "waiting", "Waiting for the first event" + (" (webhook)" if webhook else "")
    return {**info, "health": health, "health_detail": detail}


def _connector_to_dict(c: ConnectorModel) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "connector_type": c.connector_type,
        "description": c.description,
        "enabled": c.enabled,
        "config": _mask_secrets(c.config),
        "mapping_rules": c.mapping_rules,
        "ocsf_class_uid": c.ocsf_class_uid,
        "events_processed": c.events_processed,
        "events_failed": c.events_failed,
        "last_event_at": c.last_event_at.isoformat() if c.last_event_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "webhook_url": f"/api/connectors/webhooks/{c.connector_type}/{c.id}",
    }


def _mask_secrets(config: dict) -> dict:
    secret_keys = {"api_token", "api_key", "password", "secret", "client_secret", "shared_key",
                   "token", "webhook_secret", "service_account_json", "aws_secret_access_key",
                   "hec_token", "signing_secret"}
    if not config:
        return {}
    return {
        k: "***" if k in secret_keys or "secret" in k.lower() or "password" in k.lower() else v
        for k, v in config.items()
    }
