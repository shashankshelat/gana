from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.cost_tracker import estimate_monthly_cost
from app.models.forwarder import ForwarderModel
from app.models.user import UserModel
from app.api.auth import get_current_user
from app.processors.pipeline import get_pipeline_stats

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/estimate")
async def get_cost_estimate(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_pipeline_stats()
    events_per_second = stats.get("throughput_per_second", 0.0)

    result = await db.execute(
        select(ForwarderModel).where(ForwarderModel.enabled == True)
    )
    forwarders = result.scalars().all()
    types = [f.forwarder_type for f in forwarders]

    return await estimate_monthly_cost(events_per_second, types)
