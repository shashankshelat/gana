import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select, update

from app.core.config import settings
from app.core.kafka_client import consume_events
from app.forwarders.base import BaseForwarder
from app.forwarders.registry import instantiate_forwarder
from app.core.ingestion_tracker import record_volume, record_counter, event_size

logger = logging.getLogger(__name__)

# Forwarder config lives in the DB and can change from any uvicorn worker,
# so re-read it periodically instead of relying on an in-process cache.
_REFRESH_SECONDS = 10

_forwarders: list[tuple[BaseForwarder, dict, str]] = []  # (instance, filter_rules, forwarder_type)
_loaded_at = 0.0


async def _load_forwarders() -> None:
    global _forwarders, _loaded_at
    from app.core.database import AsyncSessionLocal
    from app.models.forwarder import ForwarderModel

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ForwarderModel).where(ForwarderModel.enabled == True))  # noqa: E712
        rows = result.scalars().all()

    loaded = []
    for f in rows:
        instance = instantiate_forwarder(f.forwarder_type, f.id, f.config or {})
        if instance is None:
            logger.warning("Unknown forwarder type %s for forwarder %s", f.forwarder_type, f.id)
            continue
        loaded.append((instance, f.filter_rules or {}, f.forwarder_type))
    _forwarders = loaded
    _loaded_at = time.time()


async def _record_stats(forwarder_id: str, success: int, failed: int) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models.forwarder import ForwarderModel

    values = {
        "events_forwarded": ForwarderModel.events_forwarded + success,
        "events_failed": ForwarderModel.events_failed + failed,
    }
    if success:
        values["last_forwarded_at"] = datetime.utcnow()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(update(ForwarderModel).where(ForwarderModel.id == forwarder_id).values(**values))
            await db.commit()
    except Exception as e:
        logger.error("Failed to update stats for forwarder %s: %s", forwarder_id, e)


async def _send(instance: BaseForwarder, filter_rules: dict, forwarder_type: str,
                events: list[dict], sizes: dict[int, int]) -> None:
    from app.core.metrics import events_forwarded, events_failed, forwarder_duration

    batch = instance.apply_filter(events, filter_rules)
    if not batch:
        return
    start = time.time()
    try:
        success, failed = await instance.forward(batch)
    except Exception as e:
        logger.error("Forwarder %s (%s) raised: %s", instance.forwarder_id, forwarder_type, e)
        success, failed = 0, len(batch)
    forwarder_duration.labels(forwarder_type=forwarder_type).observe(time.time() - start)
    events_forwarded.labels(forwarder_type=forwarder_type).inc(success)
    record_counter("forwarded", success)
    if success:
        # Forwarders report counts, not which events failed, so prorate bytes on partial success
        batch_bytes = sum(sizes[id(e)] for e in batch)
        record_volume("forwarder", instance.forwarder_id, success, batch_bytes * success // len(batch))
    if failed:
        events_failed.labels(error_type="forward_failed", connector_type=forwarder_type).inc(failed)
    await _record_stats(instance.forwarder_id, success, failed)


async def dispatch_mapped_events(events: list[dict]) -> None:
    if time.time() - _loaded_at > _REFRESH_SECONDS:
        await _load_forwarders()
    if not _forwarders:
        return
    sizes = {id(e): event_size(e) for e in events}
    await asyncio.gather(*(_send(inst, rules, ftype, events, sizes) for inst, rules, ftype in _forwarders))


async def start_forward_dispatcher() -> None:
    logger.info("Starting forwarder dispatcher on topic %s", settings.kafka_topic_mapped)
    await consume_events(
        topics=[settings.kafka_topic_mapped],
        # Separate group from the mapping workers so each mapped event is delivered once per forwarder
        group_id=f"{settings.kafka_consumer_group}-forwarders",
        handler=dispatch_mapped_events,
        batch_size=settings.kafka_batch_size,
    )
