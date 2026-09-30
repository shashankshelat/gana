import uuid
import logging
from datetime import datetime
from typing import Optional

from app.core.database import AsyncSessionLocal
from app.models.audit_log import AuditLogModel

logger = logging.getLogger(__name__)


async def log_action(
    action: str,
    username: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "success",
):
    try:
        async with AsyncSessionLocal() as db:
            entry = AuditLogModel(
                id=str(uuid.uuid4()),
                username=username,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                detail=detail or {},
                ip_address=ip_address,
                user_agent=user_agent,
                status=status,
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            await db.commit()
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)


def get_client_ip(request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None)
