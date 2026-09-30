import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_POLLS = 8
_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def _acquire_poll_lock(connector_id: str) -> bool:
    """Every uvicorn worker runs this scheduler; the lock ensures one worker polls each connector per interval."""
    try:
        r = await _get_redis()
        ttl = max(settings.poll_interval_seconds - 5, 5)
        return bool(await r.set(f"ocsf:poll-lock:{connector_id}", "1", nx=True, ex=ttl))
    except Exception as e:
        logger.error("Redis unavailable, skipping poll of %s to avoid duplicates: %s", connector_id, e)
        return False


def _parse_time_ms(value: Any) -> Optional[int]:
    """Parse a vendor timestamp to epoch ms; None if unrecognised (unlike normalize_timestamp, never guesses 'now')."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 1e12 else int(value * 1000)
    if isinstance(value, str):
        s = value.strip()
        if s.replace(".", "", 1).isdigit():
            return _parse_time_ms(float(s))
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = None
            for fmt in ("%Y/%m/%d %H:%M:%S", "%a %b %d %H:%M:%S %Y"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    return None


def _time_path(mapping_rules: dict) -> Optional[str]:
    rule = (mapping_rules or {}).get("time")
    if isinstance(rule, str) and not rule.startswith("$const:"):
        return rule
    if isinstance(rule, dict):
        return rule.get("path")
    return None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def has_enabled_forwarder(db) -> bool:
    from app.models.forwarder import ForwarderModel
    result = await db.execute(select(ForwarderModel.id).where(ForwarderModel.enabled == True).limit(1))  # noqa: E712
    return result.first() is not None


async def poll_connector(connector_id: str) -> dict:
    """Fetch new events for one connector, drop ones at/before the checkpoint, ingest the rest, advance the checkpoint."""
    from app.core.database import AsyncSessionLocal
    from app.models.connector import ConnectorModel
    from app.models.poll_state import ConnectorPollStateModel
    from app.connectors.registry import instantiate_connector
    from app.processors.pipeline import ingest_raw_events

    async with AsyncSessionLocal() as db:
        connector = await db.get(ConnectorModel, connector_id)
        if not connector or not connector.enabled:
            return {"skipped": "connector missing or disabled"}
        state = await db.get(ConnectorPollStateModel, connector_id)
        if state is None:
            state = ConnectorPollStateModel(connector_id=connector_id)
            db.add(state)

        state.last_polled_at = datetime.utcnow()
        if not await has_enabled_forwarder(db):
            # Leave events at the source (checkpoint untouched) rather than ingesting with nowhere to send them
            state.last_status = "skipped"
            state.last_error = "No enabled forwarder"
            await db.commit()
            return {"skipped": "no enabled forwarder"}

        poll_started_ms = int(time.time() * 1000)
        checkpoint = state.checkpoint_ms or poll_started_ms - settings.poll_initial_lookback_minutes * 60_000
        try:
            instance = instantiate_connector(
                connector.connector_type, connector_id, connector.config, connector.mapping_rules
            )
            if not instance:
                raise RuntimeError(f"Unknown connector type {connector.connector_type}")
            configured, reason = instance.polling_configured()
            if not configured:
                state.last_status = "skipped"
                state.last_error = reason
                await db.commit()
                return {"skipped": reason}
            raw_events = await instance.fetch_events(since=_iso(checkpoint))
        except Exception as e:
            state.last_status = "error"
            state.last_error = f"{type(e).__name__}: {e}"[:1000]
            await db.commit()
            logger.error("Poll failed for connector %s (%s): %s", connector_id, connector.connector_type, e)
            return {"error": state.last_error}

        # Many vendor APIs here ignore `since`, so dedupe on the event's own time field
        path = _time_path(connector.mapping_rules)
        new_events, newest = [], None
        for ev in raw_events:
            ts = _parse_time_ms(instance.get_nested(ev, path)) if path else None
            if ts is not None:
                if ts <= checkpoint:
                    continue
                newest = ts if newest is None else max(newest, ts)
            new_events.append(ev)

        success = failed = 0
        if new_events:
            success, failed = await ingest_raw_events(
                connector_id=connector_id,
                connector_type=connector.connector_type,
                raw_events=new_events,
            )
            connector.events_processed += success
            connector.events_failed += failed
            connector.last_event_at = datetime.utcnow()

        if failed == 0:
            # Without parseable event times, fall back to the poll start so the window still moves forward
            if newest is not None:
                state.checkpoint_ms = newest
            elif new_events:
                # Events without parseable times: fall back to the poll start so the window still moves
                state.checkpoint_ms = poll_started_ms
            elif state.checkpoint_ms is None:
                state.checkpoint_ms = checkpoint
            # Otherwise keep it: vendors can surface events late, so don't jump ahead to "now" on an empty poll
        state.last_status = "success" if failed == 0 else "error"
        state.last_error = None if failed == 0 else f"{failed} events failed to queue"
        state.last_events = len(new_events)
        await db.commit()

    if new_events:
        logger.info("Polled connector %s: fetched=%d new=%d queued=%d",
                    connector_id, len(raw_events), len(new_events), success)
    return {"events_fetched": len(raw_events), "new_events": len(new_events), "queued": success, "failed": failed}


async def run_scheduled_polls() -> None:
    from app.core.database import AsyncSessionLocal
    from app.models.connector import ConnectorModel
    from app.connectors.registry import get_connector_class

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ConnectorModel.id, ConnectorModel.connector_type)
                                  .where(ConnectorModel.enabled == True))  # noqa: E712
        rows = result.all()

    pollable = [cid for cid, ctype in rows
                if (cls := get_connector_class(ctype)) and cls.meta.supports_polling]
    if not pollable:
        return

    sem = asyncio.Semaphore(_MAX_CONCURRENT_POLLS)

    async def _one(cid: str):
        if not await _acquire_poll_lock(cid):
            return
        async with sem:
            try:
                await poll_connector(cid)
            except Exception as e:
                logger.error("Unexpected poll error for connector %s: %s", cid, e)

    await asyncio.gather(*(_one(cid) for cid in pollable))
