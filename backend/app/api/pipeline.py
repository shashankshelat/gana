from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.processors.pipeline import get_pipeline_stats
from app.core.ingestion_tracker import read_pipeline_history

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_ws_clients: list[WebSocket] = []


@router.get("/stats")
async def get_stats():
    return await get_pipeline_stats()


@router.get("/history")
async def get_history(minutes: int = Query(60, ge=5, le=2880)):
    """Per-minute counts from the DB, so charts are populated on page load and after restarts."""
    return await read_pipeline_history(minutes)


@router.websocket("/stream")
async def pipeline_stream(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        import asyncio
        while True:
            stats = await get_pipeline_stats()
            await websocket.send_json(stats)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)
    except Exception:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
