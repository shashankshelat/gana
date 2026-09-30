import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.models.settings import SettingModel, DEFAULTS
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role
from app.core.pii_detector import get_available_patterns
from app.core.secret_box import decrypt, encrypt, is_encrypted

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

SECRET_MASK = "••••••••"


class SettingUpdate(BaseModel):
    value: str


class BulkUpdate(BaseModel):
    settings: dict[str, str]


@router.get("")
async def get_settings(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SettingModel))
    rows = {r.key: r for r in result.scalars().all()}

    output = {}
    for key, (default, is_secret, description) in DEFAULTS.items():
        row = rows.get(key)
        value = row.value if row else default
        output[key] = {
            "value": SECRET_MASK if is_secret and value else value,
            "is_secret": is_secret,
            "description": description,
            "is_set": bool(row and row.value),
        }
    return output


@router.patch("")
async def update_settings(
    body: BulkUpdate,
    current_user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    for key, value in body.settings.items():
        if key not in DEFAULTS:
            continue
        is_secret = DEFAULTS[key][1]
        if is_secret and value == SECRET_MASK:
            continue

        if is_secret and value:
            value = encrypt(value)
        result = await db.execute(select(SettingModel).where(SettingModel.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            row.updated_by = current_user.username
        else:
            db.add(SettingModel(
                key=key,
                value=value,
                is_secret=is_secret,
                description=DEFAULTS[key][2],
                updated_by=current_user.username,
            ))
    return {"updated": len(body.settings)}


@router.get("/pii/patterns")
async def get_pii_patterns(current_user: UserModel = Depends(get_current_user)):
    return get_available_patterns()


async def get_setting_value(key: str, default: str = "") -> str:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SettingModel).where(SettingModel.key == key))
        row = result.scalar_one_or_none()
        value = decrypt(row.value) if row else ""
        return value or default


async def ensure_defaults():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SettingModel))
        existing = {r.key for r in result.scalars().all()}
        for key, (default_val, is_secret, description) in DEFAULTS.items():
            if key not in existing:
                db.add(SettingModel(key=key, value=default_val, is_secret=is_secret, description=description))
        # Secrets saved before encryption existed are encrypted in place
        for row in (await db.execute(select(SettingModel))).scalars().all():
            if DEFAULTS.get(row.key, (None, False))[1] and row.value and not is_encrypted(row.value):
                row.value = encrypt(row.value)
        await db.commit()


class AITestBody(BaseModel):
    provider: str = "claude"
    # Optional: test a key before saving it; otherwise the saved key is used
    api_key: Optional[str] = None


@router.post("/ai/test")
async def test_ai_provider(
    body: AITestBody,
    current_user: UserModel = Depends(require_role("admin")),
):
    """Check an AI key with a call that costs no tokens (listing models)."""
    key = body.api_key if body.api_key and body.api_key != SECRET_MASK else await get_setting_value(f"ai.{body.provider}_api_key")
    if not key:
        return {"success": False, "message": f"No API key saved for {body.provider}."}
    if body.provider != "claude":
        return {"success": False, "message": "Connection test is available for Anthropic Claude only."}

    import anthropic
    from app.core.ai_mapper import AI_PROVIDERS
    client = anthropic.AsyncAnthropic(api_key=key, max_retries=0, timeout=20)
    try:
        page = await client.models.list(limit=100)
        available = {m.id for m in page.data}
        model = AI_PROVIDERS["claude"]["default_model"]
        if model not in available:
            return {"success": True, "message": f"Key works, but {model} (GANA's default) is not available to it."}
        return {"success": True, "message": f"Connected to Anthropic. {model} is available."}
    except anthropic.AuthenticationError:
        return {"success": False, "message": "Anthropic rejected the key (invalid or revoked)."}
    except anthropic.PermissionDeniedError:
        return {"success": False, "message": "The key is valid but lacks permission (check the workspace)."}
    except anthropic.APIConnectionError:
        return {"success": False, "message": "Could not reach api.anthropic.com from the GANA server."}
    except anthropic.APIStatusError as e:
        return {"success": False, "message": f"Anthropic API error {e.status_code}."}
