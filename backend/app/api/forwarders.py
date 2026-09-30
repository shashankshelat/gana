import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.forwarder import ForwarderModel
from app.models.connector import ConnectorModel
from app.forwarders.registry import list_forwarder_types, instantiate_forwarder, get_forwarder_class

router = APIRouter(prefix="/api/forwarders", tags=["forwarders"])


class ForwarderCreate(BaseModel):
    name: str
    forwarder_type: str
    description: Optional[str] = None
    enabled: bool = True
    config: dict = {}
    filter_rules: dict = {}
    batch_size: int = 100
    flush_interval_ms: int = 1000


class ForwarderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    filter_rules: Optional[dict] = None
    batch_size: Optional[int] = None
    flush_interval_ms: Optional[int] = None


@router.get("/types")
async def get_forwarder_types():
    return list_forwarder_types()


@router.get("")
async def list_forwarders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ForwarderModel))
    forwarders = result.scalars().all()
    return [_forwarder_to_dict(f) for f in forwarders]


@router.post("", status_code=201)
async def create_forwarder(body: ForwarderCreate, db: AsyncSession = Depends(get_db)):
    cls = get_forwarder_class(body.forwarder_type)
    if not cls:
        raise HTTPException(400, f"Unknown forwarder type: {body.forwarder_type}")

    forwarder = ForwarderModel(
        id=str(uuid.uuid4()),
        name=body.name,
        forwarder_type=body.forwarder_type,
        description=body.description,
        enabled=body.enabled,
        config=body.config,
        filter_rules=body.filter_rules,
        batch_size=body.batch_size,
        flush_interval_ms=body.flush_interval_ms,
    )
    db.add(forwarder)
    await db.flush()
    return _forwarder_to_dict(forwarder)


@router.get("/{forwarder_id}")
async def get_forwarder(forwarder_id: str, db: AsyncSession = Depends(get_db)):
    forwarder = await _get_or_404(forwarder_id, db)
    return _forwarder_to_dict(forwarder)


@router.patch("/{forwarder_id}")
async def update_forwarder(forwarder_id: str, body: ForwarderUpdate, db: AsyncSession = Depends(get_db)):
    forwarder = await _get_or_404(forwarder_id, db)
    updates = body.model_dump(exclude_none=True)
    if updates.get("enabled") is False and forwarder.enabled:
        await _ensure_not_last_forwarder(forwarder_id, db)
    if "config" in updates:
        # The UI receives secrets masked as "***"; don't let a round-trip overwrite the stored value
        existing = forwarder.config or {}
        updates["config"] = {
            k: existing.get(k, v) if v == "***" else v
            for k, v in updates["config"].items()
        }
    for key, value in updates.items():
        setattr(forwarder, key, value)
    forwarder.updated_at = datetime.utcnow()
    return _forwarder_to_dict(forwarder)


@router.delete("/{forwarder_id}", status_code=204)
async def delete_forwarder(forwarder_id: str, db: AsyncSession = Depends(get_db)):
    forwarder = await _get_or_404(forwarder_id, db)
    if forwarder.enabled:
        await _ensure_not_last_forwarder(forwarder_id, db)
    await db.delete(forwarder)


@router.post("/{forwarder_id}/test")
async def test_forwarder(forwarder_id: str, db: AsyncSession = Depends(get_db)):
    forwarder = await _get_or_404(forwarder_id, db)
    instance = instantiate_forwarder(forwarder.forwarder_type, forwarder_id, forwarder.config)
    if not instance:
        raise HTTPException(400, "Cannot instantiate forwarder")
    success, message = await instance.test_connection()
    return {"success": success, "message": message}


@router.post("/{forwarder_id}/flush")
async def flush_forwarder(forwarder_id: str, db: AsyncSession = Depends(get_db)):
    forwarder = await _get_or_404(forwarder_id, db)
    return {"message": f"Flush triggered for {forwarder.name}"}


async def _ensure_not_last_forwarder(forwarder_id: str, db: AsyncSession) -> None:
    """Connectors need somewhere to send events, so keep at least one enabled forwarder while any exist."""
    others = await db.execute(
        select(ForwarderModel.id).where(ForwarderModel.enabled == True, ForwarderModel.id != forwarder_id).limit(1)  # noqa: E712
    )
    if others.first() is None:
        connectors = await db.execute(select(ConnectorModel.id).limit(1))
        if connectors.first() is not None:
            raise HTTPException(409, "This is the only enabled forwarder and connectors depend on it. "
                                     "Add another forwarder or remove the connectors first.")


async def _get_or_404(forwarder_id: str, db: AsyncSession) -> ForwarderModel:
    result = await db.execute(select(ForwarderModel).where(ForwarderModel.id == forwarder_id))
    forwarder = result.scalar_one_or_none()
    if not forwarder:
        raise HTTPException(404, "Forwarder not found")
    return forwarder


def _forwarder_to_dict(f: ForwarderModel) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "forwarder_type": f.forwarder_type,
        "description": f.description,
        "enabled": f.enabled,
        "config": _mask_secrets(f.config),
        "filter_rules": f.filter_rules,
        "batch_size": f.batch_size,
        "flush_interval_ms": f.flush_interval_ms,
        "events_forwarded": f.events_forwarded,
        "events_failed": f.events_failed,
        "last_forwarded_at": f.last_forwarded_at.isoformat() if f.last_forwarded_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _mask_secrets(config: dict) -> dict:
    secret_keys = {"token", "password", "secret", "api_key", "shared_key", "hec_token",
                   "client_secret", "http_source_url", "aws_secret_access_key"}
    if not config:
        return {}
    return {
        k: "***" if k in secret_keys or "secret" in k.lower() or "password" in k.lower() or "token" in k.lower() else v
        for k, v in config.items()
    }
