from fastapi import APIRouter
from app.core.config import settings
from app.core.schema_manager import schema_manager

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    version_info = schema_manager.get_version_info()
    return {
        "status": "healthy",
        "version": settings.app_version,
        "ocsf_schema_version": version_info.get("version") if version_info else "not_loaded",
    }


@router.get("/api/stats/overview")
async def overview_stats():
    from app.processors.pipeline import get_pipeline_stats
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal
    from app.models.connector import ConnectorModel
    from app.models.forwarder import ForwarderModel

    stats = await get_pipeline_stats()
    async with AsyncSessionLocal() as db:
        conn_count = await db.scalar(select(func.count()).select_from(ConnectorModel))
        fwd_count = await db.scalar(select(func.count()).select_from(ForwarderModel))
        conn_enabled = await db.scalar(
            select(func.count()).select_from(ConnectorModel).where(ConnectorModel.enabled == True)
        )

    return {
        **stats,
        "total_connectors": conn_count,
        "enabled_connectors": conn_enabled,
        "total_forwarders": fwd_count,
    }
