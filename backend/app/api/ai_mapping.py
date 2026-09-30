import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ai_mapper import generate_mapping, validate_mapping_against_schema, AI_PROVIDERS
from app.models.approval import MappingApprovalModel, UnknownFieldModel
from app.models.connector import ConnectorModel
from app.models.user import UserModel
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai-mapping"])


class AnalyzeRequest(BaseModel):
    sample_logs: str
    connector_id: Optional[str] = None
    connector_type: str
    ocsf_class_uid: int = 3002
    provider: str = "claude"
    model: Optional[str] = None
    api_key: str


@router.get("/providers")
async def get_providers():
    return AI_PROVIDERS


@router.post("/analyze")
async def analyze_logs(
    body: AnalyzeRequest,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.provider not in AI_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}. Choose from: {list(AI_PROVIDERS.keys())}")
    if not body.sample_logs.strip():
        raise HTTPException(400, "sample_logs cannot be empty")

    model = body.model or AI_PROVIDERS[body.provider]["default_model"]

    try:
        result = await generate_mapping(
            sample_logs=body.sample_logs,
            connector_type=body.connector_type,
            ocsf_class_uid=body.ocsf_class_uid,
            provider=body.provider,
            model=model,
            api_key=body.api_key,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"AI provider error: {e}")

    connector_name = body.connector_type
    current_mapping = {}
    if body.connector_id:
        conn = await db.execute(select(ConnectorModel).where(ConnectorModel.id == body.connector_id))
        conn_obj = conn.scalar_one_or_none()
        if conn_obj:
            connector_name = conn_obj.name
            current_mapping = conn_obj.mapping_rules or {}

    known, schema_unknown = validate_mapping_against_schema(result["mapping"], body.ocsf_class_uid)

    approval = MappingApprovalModel(
        id=str(uuid.uuid4()),
        connector_id=body.connector_id,
        connector_type=body.connector_type,
        connector_name=connector_name,
        ocsf_class_uid=body.ocsf_class_uid,
        source="ai",
        ai_provider=body.provider,
        ai_model=model,
        sample_logs=body.sample_logs[:5000],
        proposed_mapping=result["mapping"],
        current_mapping=current_mapping,
        ai_explanation=result.get("explanation", ""),
        status="pending",
        created_by=current_user.username,
    )
    db.add(approval)

    unknown_field_ids = []
    for uf in result.get("unknown_fields", []):
        unk = UnknownFieldModel(
            id=str(uuid.uuid4()),
            approval_id=approval.id,
            connector_type=body.connector_type,
            field_name=uf.get("field_name", "unknown"),
            field_path=uf.get("field_path", ""),
            sample_values=uf.get("sample_values", []),
            ai_description=uf.get("description", ""),
            ai_suggested_ocsf_path=uf.get("suggested_ocsf_path", ""),
            status="pending",
        )
        db.add(unk)
        unknown_field_ids.append(unk.id)

    await db.flush()

    return {
        "approval_id": approval.id,
        "proposed_mapping": result["mapping"],
        "current_mapping": current_mapping,
        "explanation": result.get("explanation", ""),
        "ocsf_class_uid": body.ocsf_class_uid,
        "schema_validation": {
            "known_fields": known,
            "unknown_ocsf_fields": schema_unknown,
        },
        "unknown_source_fields": result.get("unknown_fields", []),
        "unknown_field_count": len(result.get("unknown_fields", [])),
        "provider": body.provider,
        "model": model,
        "status": "pending_approval",
    }
