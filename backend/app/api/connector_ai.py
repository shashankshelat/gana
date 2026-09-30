"""AI mapping, per connector: settings for automatic proposals from failed events, and manual runs."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.core import ai_autofix
from app.core.database import get_db
from app.models.approval import ApprovalDLQLinkModel, MappingApprovalModel
from app.models.connector import ConnectorModel
from app.models.user import UserModel

router = APIRouter(prefix="/api/connectors/{connector_id}/ai", tags=["connector-ai"])


class AISettingsUpdate(BaseModel):
    auto_enabled: Optional[bool] = None
    min_events: Optional[int] = Field(None, ge=1, le=10000)
    cooldown_minutes: Optional[int] = Field(None, ge=5, le=10080)
    daily_limit: Optional[int] = Field(None, ge=0, le=500)
    max_samples: Optional[int] = Field(None, ge=1, le=50)


class SamplesBody(BaseModel):
    sample_logs: str


async def _connector(db: AsyncSession, connector_id: str) -> ConnectorModel:
    c = await db.get(ConnectorModel, connector_id)
    if not c:
        raise HTTPException(404, "Connector not found")
    return c


def _settings_dict(ai) -> dict:
    return {
        "auto_enabled": ai.auto_enabled, "min_events": ai.min_events, "cooldown_minutes": ai.cooldown_minutes,
        "daily_limit": ai.daily_limit, "max_samples": ai.max_samples,
        "last_run_at": ai.last_run_at.isoformat() if ai.last_run_at else None,
        "last_status": ai.last_status, "last_message": ai.last_message,
        "runs_today": ai.runs_today or 0, "runs_day": ai.runs_day,
    }


@router.get("")
async def get_ai(connector_id: str, current_user: UserModel = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _connector(db, connector_id)
    ai = await ai_autofix.get_settings(db, connector_id)
    provider, model, key = await ai_autofix.ai_provider_config()
    proposals = (await db.execute(
        select(MappingApprovalModel).where(MappingApprovalModel.connector_id == connector_id)
        .order_by(MappingApprovalModel.created_at.desc()).limit(15)
    )).scalars().all()
    links = {l.approval_id: len(l.dlq_event_ids or []) for l in (await db.execute(
        select(ApprovalDLQLinkModel).where(ApprovalDLQLinkModel.approval_id.in_([p.id for p in proposals]))
    )).scalars().all()} if proposals else {}
    unlinked = await ai_autofix.unlinked_failed_events(db, connector_id)
    return {
        "settings": _settings_dict(ai),
        "provider": provider, "model": model, "key_configured": bool(key),
        "failed_events_uncovered": len(unlinked),
        "proposals": [{
            "id": p.id, "status": p.status, "source": p.source, "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "reviewed_by": p.reviewed_by, "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "routes": len((p.proposed_mapping or {}).get("_routes") or []),
            "rules": len([k for k in (p.proposed_mapping or {}) if not k.startswith("_")]),
            "failed_events": links.get(p.id, 0),
            "explanation": (p.ai_explanation or "")[:600],
        } for p in proposals],
    }


@router.put("")
async def update_ai(connector_id: str, body: AISettingsUpdate,
                    current_user: UserModel = Depends(require_role("admin", "reviewer")), db: AsyncSession = Depends(get_db)):
    await _connector(db, connector_id)
    ai = await ai_autofix.get_settings(db, connector_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ai, k, v)
    return _settings_dict(ai)


@router.post("/run")
async def run_now(connector_id: str, current_user: UserModel = Depends(require_role("admin", "reviewer"))):
    """Propose a mapping now from every failed event not already covered by a pending proposal."""
    result = await ai_autofix.propose(connector_id, source=ai_autofix.SOURCE_MANUAL, created_by=current_user.username)
    if result["status"] == "error":
        raise HTTPException(502, result["message"])
    return result


@router.post("/samples")
async def from_samples(connector_id: str, body: SamplesBody,
                       current_user: UserModel = Depends(require_role("admin", "reviewer"))):
    """Propose a mapping from analyst-pasted events (a JSON array, one JSON object, or JSON lines)."""
    text = body.sample_logs.strip()
    try:
        parsed = json.loads(text)
        samples = parsed if isinstance(parsed, list) else [parsed]
    except ValueError:
        try:
            samples = [json.loads(line) for line in text.splitlines() if line.strip()]
        except ValueError:
            raise HTTPException(422, "Samples must be JSON: an array, a single object, or one object per line")
    samples = [s for s in samples if isinstance(s, dict)]
    if not samples:
        raise HTTPException(422, "No JSON objects found in the samples")
    result = await ai_autofix.propose(connector_id, source=ai_autofix.SOURCE_SAMPLES,
                                      created_by=current_user.username, samples=samples)
    if result["status"] == "error":
        raise HTTPException(502, result["message"])
    return result
