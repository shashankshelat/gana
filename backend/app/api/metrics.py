from fastapi import APIRouter, Response
from app.core.metrics import get_metrics_output

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics():
    data, content_type = get_metrics_output()
    return Response(content=data, media_type=content_type)
