import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from app.core.kafka_client import produce_batch, consume_events
from app.core.config import settings
from app.core.mapping_cache import mapping_cache
from app.processors.mapper import ocsf_mapper, mapping_status, stamp_mapping_status

logger = logging.getLogger(__name__)

_started_at: float | None = None


async def get_pipeline_stats() -> dict:
    """Pipeline totals from the DB (see ingestion_tracker) so they survive restarts and match across workers."""
    from app.core.ingestion_tracker import read_pipeline_stats
    return {**await read_pipeline_stats(), "started_at": _started_at}


async def _get_pii_config() -> tuple[bool, list[str], str]:
    try:
        from app.api.settings import get_setting_value
        enabled = (await get_setting_value("pii.enabled", "false")).lower() == "true"
        if not enabled:
            return False, [], "mask"
        patterns_raw = await get_setting_value("pii.patterns", '["email","credit_card"]')
        patterns = json.loads(patterns_raw)
        mode = await get_setting_value("pii.mode", "mask")
        return True, patterns, mode
    except Exception:
        return False, [], "mask"


async def _write_to_dlq(raw_event: dict, error_message: str, error_type: str):
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.dlq import DLQEventModel

        connector_id = raw_event.get("_connector_id")
        connector_type = raw_event.get("_connector_type", "unknown")

        async with AsyncSessionLocal() as db:
            entry = DLQEventModel(
                id=str(uuid.uuid4()),
                connector_id=connector_id,
                connector_type=connector_type,
                raw_event=raw_event,
                error_message=error_message[:1000],
                error_type=error_type,
            )
            db.add(entry)
            await db.commit()
    except Exception as e:
        logger.error("Failed to write to DLQ: %s", e)


async def process_raw_events(events: list[dict]) -> None:
    from app.core.metrics import events_received, events_mapped, events_failed, mapping_duration
    from app.core.pii_detector import detect_and_mask
    from app.core.anomaly_detector import record_events, check_for_anomalies, persist_anomalies
    from app.core.ingestion_tracker import scan_unmapped, paths_for_event, record_counter, record_volume

    # DLQ retries were already counted as received (and as failed) the first time round
    retries = sum(1 for e in events if e.get("_dlq_retry"))
    record_counter("received", len(events) - retries)
    mapped_events = []
    failed = 0

    pii_enabled, pii_patterns, pii_mode = await _get_pii_config()
    await mapping_cache.refresh_if_stale()

    connector_counts: dict[str, int] = {}

    for event in events:
        connector_id = event.get("_connector_id", "unknown")
        connector_type = event.get("_connector_type", "unknown")
        raw = event.get("_raw_data", event)

        events_received.labels(connector_type=connector_type).inc()
        connector_counts[connector_id] = connector_counts.get(connector_id, 0) + 1

        # Look up mapping rules from the in-memory cache — O(1), no per-event JSON
        cached = await mapping_cache.get_or_load(connector_id)
        if not cached or not cached.get("mapping_rules"):
            events_failed.labels(error_type="no_mapping_rules", connector_type=connector_type).inc()
            # A DLQ retry that fails again is the same event, already counted once
            failed += 0 if event.get("_dlq_retry") else 1
            await _write_to_dlq(event, "No mapping rules configured for this connector", "no_mapping_rules")
            continue

        mapping_rules = cached["mapping_rules"]
        ocsf_class_uid = cached["ocsf_class_uid"]

        start_ts = time.time()
        try:
            mapped = ocsf_mapper.map_event(
                raw_event=raw,
                connector_id=connector_id,
                connector_type=connector_type,
                mapping_rules=mapping_rules,
                ocsf_class_uid=ocsf_class_uid,
            )
            mapping_duration.labels(connector_type=connector_type).observe(time.time() - start_ts)

            route = ocsf_mapper.match_route(raw, mapping_rules)
            scan_unmapped(connector_id, connector_type, raw, paths_for_event(mapping_rules, route),
                          scope=(route or {}).get("name", ""))
            status = mapping_status(mapping_rules, route, mapped.get("class_uid", ocsf_class_uid))
            stamp_mapping_status(mapped, status)
            record_volume(f"mapping_{status}", connector_id, 1, 0)

            if pii_enabled and pii_patterns:
                mapped, _ = detect_and_mask(mapped, pii_patterns, pii_mode)

            mapped_events.append(mapped)
            if event.get("_dlq_retry"):
                record_counter("failed", -1)
            events_mapped.labels(class_uid=str(mapped.get("class_uid", ocsf_class_uid)), connector_type=connector_type).inc()
        except Exception as e:
            logger.error("Mapping error for connector %s: %s", connector_id, e)
            events_failed.labels(error_type=type(e).__name__, connector_type=connector_type).inc()
            failed += 0 if event.get("_dlq_retry") else 1
            await _write_to_dlq(event, str(e), type(e).__name__)

    record_counter("failed", failed)
    record_counter("mapped", len(mapped_events))

    for connector_id, count in connector_counts.items():
        record_events(connector_id, count)

    # AI proposals for failed events come from the ai_autofix scheduler job, not from here
    if mapped_events:
        # Delivery to destinations happens in forward_dispatcher, which consumes this topic
        await produce_batch(settings.kafka_topic_mapped, mapped_events)


async def ingest_raw_events(
    connector_id: str,
    connector_type: str,
    raw_events: list[dict],
    dlq_retry: bool = False,
) -> tuple[int, int]:
    """
    Wrap raw events with connector metadata and publish to Kafka.
    Mapping rules are NOT embedded in messages — pipeline workers look them up
    from the in-memory MappingCache by connector_id.
    """
    from app.core.ingestion_tracker import record_volume, event_size
    if not dlq_retry:
        record_volume("connector", connector_id, len(raw_events), sum(event_size(e) for e in raw_events))

    wrapped = [
        {
            "_connector_id": connector_id,
            "_connector_type": connector_type,
            "_raw_data": event,
            **({"_dlq_retry": True} if dlq_retry else {}),
        }
        for event in raw_events
    ]

    batch_size = settings.kafka_batch_size
    total_success = 0
    total_fail = 0

    for i in range(0, len(wrapped), batch_size):
        batch = wrapped[i:i + batch_size]
        success, fail = await produce_batch(settings.kafka_topic_raw, batch)
        total_success += success
        total_fail += fail

    return total_success, total_fail


async def start_pipeline_workers() -> None:
    global _started_at
    _started_at = time.time()
    logger.info("Starting GANA pipeline workers...")

    workers = [
        asyncio.create_task(
            consume_events(
                topics=[settings.kafka_topic_raw],
                # Shared group so workers split partitions; distinct groups would each consume every event
                group_id=settings.kafka_consumer_group,
                handler=process_raw_events,
                batch_size=settings.kafka_batch_size,
            ),
            name=f"pipeline-worker-{i}",
        )
        for i in range(settings.max_workers)
    ]

    from app.processors.forward_dispatcher import start_forward_dispatcher
    workers.append(asyncio.create_task(start_forward_dispatcher(), name="forward-dispatcher"))

    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        logger.info("Pipeline workers stopped")
        for w in workers:
            w.cancel()
