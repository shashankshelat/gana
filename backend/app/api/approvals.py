import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.approval import MappingApprovalModel, UnknownFieldModel
from app.models.connector import ConnectorModel
from app.models.user import UserModel
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ReviewBody(BaseModel):
    action: str  # "approve" or "reject"
    reviewer_note: Optional[str] = None
    edited_mapping: Optional[dict] = None


class SubmitUnknownFieldBody(BaseModel):
    github_token: str
    additional_context: Optional[str] = None


@router.get("")
async def list_approvals(
    status: Optional[str] = None,
    connector_id: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MappingApprovalModel).order_by(MappingApprovalModel.created_at.desc())
    if status:
        stmt = stmt.where(MappingApprovalModel.status == status)
    if connector_id:
        stmt = stmt.where(MappingApprovalModel.connector_id == connector_id)
    result = await db.execute(stmt)
    approvals = result.scalars().all()
    return [_approval_to_dict(a) for a in approvals]


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    approval = await _get_or_404(approval_id, db)
    unk_result = await db.execute(
        select(UnknownFieldModel).where(UnknownFieldModel.approval_id == approval_id)
    )
    unknown_fields = unk_result.scalars().all()
    return {
        **_approval_to_dict(approval),
        "unknown_fields": [_unk_to_dict(u) for u in unknown_fields],
    }


@router.post("/{approval_id}/review")
async def review_approval(
    approval_id: str,
    body: ReviewBody,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    approval = await _get_or_404(approval_id, db)
    if approval.status != "pending":
        raise HTTPException(400, f"Approval is already {approval.status}")

    final_mapping = body.edited_mapping or approval.proposed_mapping
    if body.action == "approve" and approval.connector_id:
        # Keep structural keys such as _routes that the proposal didn't include (AI proposals are flat)
        conn = await db.get(ConnectorModel, approval.connector_id)
        for key, value in ((conn.mapping_rules or {}) if conn else {}).items():
            if key.startswith("_") and key not in final_mapping:
                final_mapping = {**final_mapping, key: value}
    approval.status = "approved" if body.action == "approve" else "rejected"
    approval.reviewed_by = current_user.username
    approval.reviewer_note = body.reviewer_note
    approval.reviewed_at = datetime.utcnow()

    if body.action == "approve" and approval.connector_id:
        conn_result = await db.execute(
            select(ConnectorModel).where(ConnectorModel.id == approval.connector_id)
        )
        connector = conn_result.scalar_one_or_none()
        if connector:
            connector.mapping_rules = final_mapping
            connector.updated_at = datetime.utcnow()

        from app.core.mapping_cache import mapping_cache
        mapping_cache.update(
            approval.connector_id,
            final_mapping,
            3002 if approval.ocsf_class_uid is None else approval.ocsf_class_uid,
        )

    retried = 0
    if body.action == "approve":
        from app.models.approval import ApprovalDLQLinkModel
        from app.models.dlq import DLQEventModel
        from app.api.dlq import _requeue
        from app.core.ai_autofix import AI_SOURCES
        link = await db.get(ApprovalDLQLinkModel, approval_id)
        ids = set(link.dlq_event_ids or []) if link else set()
        stmt = select(DLQEventModel).where(DLQEventModel.discarded == False)  # noqa: E712
        if approval.source in AI_SOURCES and approval.connector_id:
            # The new mapping may also fix failures that arrived after the proposal was made
            stmt = stmt.where((DLQEventModel.id.in_(ids)) | (DLQEventModel.connector_id == approval.connector_id))
        else:
            stmt = stmt.where(DLQEventModel.id.in_(ids))
        if ids or approval.source in AI_SOURCES:
            retried, _ = await _requeue(list((await db.execute(stmt)).scalars().all()))

    return {
        **_approval_to_dict(approval),
        "mapping_applied": body.action == "approve" and approval.connector_id is not None,
        "dlq_events_retried": retried,
    }


@router.delete("/{approval_id}", status_code=204)
async def delete_approval(
    approval_id: str,
    current_user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    approval = await _get_or_404(approval_id, db)
    await db.delete(approval)


@router.get("/unknown-fields/list")
async def list_unknown_fields(
    status: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(UnknownFieldModel).order_by(UnknownFieldModel.created_at.desc())
    if status:
        stmt = stmt.where(UnknownFieldModel.status == status)
    result = await db.execute(stmt)
    fields = result.scalars().all()
    return [_unk_to_dict(f) for f in fields]


@router.post("/unknown-fields/{field_id}/submit")
async def submit_unknown_field_to_ocsf(
    field_id: str,
    body: SubmitUnknownFieldBody,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UnknownFieldModel).where(UnknownFieldModel.id == field_id))
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(404, "Unknown field not found")
    if field.status == "submitted":
        raise HTTPException(400, "Already submitted to OCSF")

    issue_title = f"[Field Proposal] Add `{field.field_name}` for {field.connector_type} logs"
    issue_body = f"""## New OCSF Field Proposal

**Submitted via:** GANA (open-source)
**Source connector:** `{field.connector_type}`
**Field name:** `{field.field_name}`
**Observed at path:** `{field.field_path or 'unknown'}`

### Description
{field.ai_description or 'No description provided.'}

### Sample Values
```
{chr(10).join(str(v) for v in (field.sample_values or [])[:5])}
```

### Suggested OCSF Path
`{field.ai_suggested_ocsf_path or 'TBD'}`

### Additional Context
{body.additional_context or 'None provided.'}

---
*This issue was auto-generated by [GANA](https://github.com/ocsf/ocsf-schema/issues) after AI analysis detected a field with no current OCSF equivalent.*
"""

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.github.com/repos/ocsf/ocsf-schema/issues",
            json={"title": issue_title, "body": issue_body, "labels": ["field-proposal"]},
            headers={
                "Authorization": f"token {body.github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(502, f"GitHub API error {resp.status_code}: {resp.text[:300]}")

        issue_data = resp.json()
        field.status = "submitted"
        field.github_issue_url = issue_data["html_url"]
        field.submitted_by = current_user.username
        field.submitted_at = datetime.utcnow()

    return {
        **_unk_to_dict(field),
        "github_issue_url": field.github_issue_url,
    }


@router.post("/unknown-fields/{field_id}/ignore")
async def ignore_unknown_field(
    field_id: str,
    current_user: UserModel = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UnknownFieldModel).where(UnknownFieldModel.id == field_id))
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(404, "Unknown field not found")
    field.status = "ignored"
    return _unk_to_dict(field)


async def _get_or_404(approval_id: str, db: AsyncSession) -> MappingApprovalModel:
    result = await db.execute(
        select(MappingApprovalModel).where(MappingApprovalModel.id == approval_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Approval not found")
    return obj


def _approval_to_dict(a: MappingApprovalModel) -> dict:
    return {
        "id": a.id,
        "connector_id": a.connector_id,
        "connector_type": a.connector_type,
        "connector_name": a.connector_name,
        "ocsf_class_uid": a.ocsf_class_uid,
        "source": a.source,
        "ai_provider": a.ai_provider,
        "ai_model": a.ai_model,
        "proposed_mapping": a.proposed_mapping,
        "current_mapping": a.current_mapping,
        "ai_explanation": a.ai_explanation,
        "status": a.status,
        "reviewed_by": a.reviewed_by,
        "reviewer_note": a.reviewer_note,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "created_by": a.created_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _unk_to_dict(u: UnknownFieldModel) -> dict:
    return {
        "id": u.id,
        "approval_id": u.approval_id,
        "connector_type": u.connector_type,
        "field_name": u.field_name,
        "field_path": u.field_path,
        "sample_values": u.sample_values,
        "ai_description": u.ai_description,
        "ai_suggested_ocsf_path": u.ai_suggested_ocsf_path,
        "status": u.status,
        "github_issue_url": u.github_issue_url,
        "submitted_by": u.submitted_by,
        "submitted_at": u.submitted_at.isoformat() if u.submitted_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
