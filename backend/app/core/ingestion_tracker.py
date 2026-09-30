"""
Ingestion volume and unmapped-field tracking.

Counters accumulate in memory per worker process and are flushed to the DB every few seconds
with additive upserts, so hot paths never touch SQLite and the 4 uvicorn workers don't conflict.
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, delete, func, select

from app.core.database import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)

_MAX_SAMPLES = 5
_MAX_SAMPLE_VALUE_CHARS = 200
_MAX_SAMPLE_EVENT_BYTES = 20_000
_MAX_DEPTH = 8
_MAX_FIELDS_PER_EVENT = 500
# Scanning every event for unmapped fields is wasted work at high volume; a bounded sample is enough
_MAX_SCANNED_PER_CONNECTOR_PER_FLUSH = 200

# (day, kind, entity_id) -> [events, bytes]
_volume: dict[tuple[str, str, str], list[int]] = {}
# (connector_id, field_path) -> {"connector_type", "count", "samples": [...], "event": dict | None}
_unmapped: dict[tuple[str, str], dict] = {}
_scanned: dict[str, int] = {}
# (bucket, name) -> count, where bucket is "total" or a UTC minute
_counters: dict[tuple[str, str], int] = {}
_last_event_ms = 0
_last_prune = 0.0

COUNTER_NAMES = ("received", "mapped", "failed", "forwarded")
_PRUNE_EVERY_SECONDS = 600
_KEEP_MINUTE_BUCKETS = timedelta(days=2)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def event_size(event: Any) -> int:
    return len(json.dumps(event, default=str, separators=(",", ":")).encode("utf-8"))


def record_volume(kind: str, entity_id: str, events: int, size_bytes: int) -> None:
    if events <= 0 and size_bytes <= 0:
        return
    slot = _volume.setdefault((_today(), kind, entity_id), [0, 0])
    slot[0] += events
    slot[1] += size_bytes


def minute_bucket(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M")


def record_counter(name: str, n: int) -> None:
    """Pipeline-wide counter (received/mapped/failed/forwarded), persisted so it survives restarts."""
    global _last_event_ms
    if n == 0:
        return
    # Negative deltas are corrections (e.g. a DLQ event later succeeding); only the all-time total changes
    for bucket in ("total", minute_bucket()) if n > 0 else ("total",):
        _counters[(bucket, name)] = _counters.get((bucket, name), 0) + n
    if name in ("received", "mapped"):
        _last_event_ms = int(time.time() * 1000)


# ── Unmapped field detection ─────────────────────────────────────────────────

def rule_source_paths(mapping_rules: dict) -> list[str]:
    """Raw paths read by the flat rules and by every route (including the fields routes branch on)."""
    rules = mapping_rules or {}
    paths = []
    for key, source in rules.items():
        if key.startswith("_"):
            continue
        if isinstance(source, str) and not source.startswith("$const:"):
            paths.append(source)
        elif isinstance(source, dict) and source.get("path"):
            paths.append(source["path"])
    for route in rules.get("_routes") or []:
        if (route.get("when") or {}).get("field"):
            paths.append(route["when"]["field"])
        paths.extend(rule_source_paths(route.get("mapping") or {}))
    return paths


def paths_for_event(mapping_rules: dict, route: dict | None) -> list[str]:
    """Raw paths read for one event: its matched route's rules (plus the field it branched on), else the flat rules."""
    if route:
        paths = rule_source_paths(route.get("mapping") or {})
        field = (route.get("when") or {}).get("field")
        return paths + [field] if field else paths
    return rule_source_paths({k: v for k, v in (mapping_rules or {}).items() if k != "_routes"})


def split_scope(field_path: str) -> tuple[str, str]:
    """Stored unmapped paths are "[route] path" for routed events; returns (route name or "", path)."""
    if field_path.startswith("[") and "] " in field_path:
        scope, path = field_path[1:].split("] ", 1)
        return scope, path
    return "", field_path


def _norm(path: str) -> str:
    return re.sub(r"\[[^\]]*\]", "[]", path)


def is_covered(leaf: str, rule_paths: list[str]) -> bool:
    # Index and attribute selectors both address a list item, so compare with selectors erased
    leaf = _norm(leaf)
    for p in map(_norm, rule_paths):
        if p == leaf:
            return True
        # Rule reads a parent object, or reads into this list/object
        if leaf.startswith(p + ".") or leaf.startswith(p + "["):
            return True
        if p.startswith(leaf + ".") or p.startswith(leaf + "["):
            return True
    return False


def _leaves(data: Any, prefix: str = "", depth: int = 0, out: list | None = None) -> list[tuple[str, Any]]:
    """Flatten to (path, value) using the same syntax as mapping rules (a.b, list[0].c)."""
    if out is None:
        out = []
    if len(out) >= _MAX_FIELDS_PER_EVENT:
        return out
    if isinstance(data, dict) and data and depth < _MAX_DEPTH:
        for k, v in data.items():
            _leaves(v, f"{prefix}.{k}" if prefix else str(k), depth + 1, out)
    elif isinstance(data, list) and data and isinstance(data[0], dict) and depth < _MAX_DEPTH:
        _leaves(data[0], f"{prefix}[0]", depth + 1, out)
    elif prefix:
        out.append((prefix, data))
    return out


def scan_unmapped(connector_id: str, connector_type: str, raw_event: dict, rule_paths: list[str],
                  scope: str = "") -> None:
    if _scanned.get(connector_id, 0) >= _MAX_SCANNED_PER_CONNECTOR_PER_FLUSH:
        return
    _scanned[connector_id] = _scanned.get(connector_id, 0) + 1
    record_volume("unmapped_scan", connector_id, 1, 0)

    for path, value in _leaves(raw_event):
        if value is None or value == "" or is_covered(path, rule_paths):
            continue
        # Prefix with the route so each event type's gaps are listed separately
        key = f"[{scope}] {path}" if scope else path
        entry = _unmapped.setdefault(
            (connector_id, key),
            {"connector_type": connector_type, "count": 0, "samples": [], "event": None},
        )
        entry["count"] += 1
        if isinstance(value, (int, float, bool)):
            sample = value
        elif isinstance(value, str):
            sample = value[:_MAX_SAMPLE_VALUE_CHARS]
        else:
            sample = json.dumps(value, default=str)[:_MAX_SAMPLE_VALUE_CHARS]
        if len(entry["samples"]) < _MAX_SAMPLES and sample not in entry["samples"]:
            entry["samples"].append(sample)
        if entry["event"] is None and event_size(raw_event) <= _MAX_SAMPLE_EVENT_BYTES:
            entry["event"] = raw_event


# ── Flush ────────────────────────────────────────────────────────────────────

def _insert(model):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


async def flush() -> None:
    global _volume, _unmapped, _scanned, _counters, _last_event_ms, _last_prune
    volume, unmapped, counters, last_event_ms = _volume, _unmapped, _counters, _last_event_ms
    _volume, _unmapped, _scanned, _counters, _last_event_ms = {}, {}, {}, {}, 0

    from app.models.ingestion import IngestionStatModel, UnmappedFieldModel, PipelineCounterModel

    try:
        async with AsyncSessionLocal() as db:
            for (bucket, name), n in counters.items():
                stmt = _insert(PipelineCounterModel).values(id=f"{bucket}|{name}", bucket=bucket, name=name, value=n)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"], set_={"value": PipelineCounterModel.value + stmt.excluded.value},
                )
                await db.execute(stmt)

            if last_event_ms:
                greatest = func.greatest if engine.dialect.name == "postgresql" else func.max
                stmt = _insert(PipelineCounterModel).values(
                    id="total|last_event_at", bucket="total", name="last_event_at", value=last_event_ms,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"value": greatest(PipelineCounterModel.value, stmt.excluded.value)},
                )
                await db.execute(stmt)

            if time.time() - _last_prune > _PRUNE_EVERY_SECONDS:
                _last_prune = time.time()
                cutoff = minute_bucket(datetime.now(timezone.utc) - _KEEP_MINUTE_BUCKETS)
                await db.execute(delete(PipelineCounterModel).where(
                    PipelineCounterModel.bucket != "total", PipelineCounterModel.bucket < cutoff,
                ))

            for (day, kind, entity_id), (events, size) in volume.items():
                stmt = _insert(IngestionStatModel).values(
                    id=f"{day}|{kind}|{entity_id}", day=day, kind=kind,
                    entity_id=entity_id, events=events, bytes=size,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "events": IngestionStatModel.events + stmt.excluded.events,
                        "bytes": IngestionStatModel.bytes + stmt.excluded.bytes,
                    },
                )
                await db.execute(stmt)

            now = datetime.utcnow()
            for (connector_id, path), e in unmapped.items():
                stmt = _insert(UnmappedFieldModel).values(
                    id=f"{connector_id}|{path}"[:600], connector_id=connector_id,
                    connector_type=e["connector_type"], field_path=path[:500],
                    occurrences=e["count"], sample_values=e["samples"], sample_event=e["event"],
                    first_seen=now, last_seen=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "occurrences": UnmappedFieldModel.occurrences + stmt.excluded.occurrences,
                        "last_seen": stmt.excluded.last_seen,
                        # Keep whichever sample set is richer (another worker may have seen more values)
                        "sample_values": case(
                            (func.json_array_length(stmt.excluded.sample_values)
                             > func.json_array_length(UnmappedFieldModel.sample_values),
                             stmt.excluded.sample_values),
                            else_=UnmappedFieldModel.sample_values,
                        ),
                        "sample_event": func.coalesce(UnmappedFieldModel.sample_event, stmt.excluded.sample_event),
                    },
                )
                await db.execute(stmt)
            await db.commit()
    except Exception as e:
        logger.error("Failed to flush ingestion stats: %s", e)


# ── Read side ────────────────────────────────────────────────────────────────

async def read_pipeline_stats() -> dict:
    """Totals and current throughput from the DB, identical from every worker and across restarts."""
    from app.models.ingestion import PipelineCounterModel

    now = datetime.now(timezone.utc)
    current, previous = minute_bucket(now), minute_bucket(now - timedelta(minutes=1))
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PipelineCounterModel.bucket, PipelineCounterModel.name, PipelineCounterModel.value)
            .where(PipelineCounterModel.bucket.in_(["total", current, previous]))
        )).all()

    totals = {n: 0 for n in COUNTER_NAMES}
    recent_mapped = 0
    last_event_ms = None
    for bucket, name, value in rows:
        if bucket == "total":
            if name == "last_event_at":
                last_event_ms = value
            elif name in totals:
                totals[name] = value
        elif name == "mapped":
            recent_mapped += value
    # Previous full minute plus the elapsed part of the current one
    window = 60 + now.second
    return {
        "events_received": totals["received"],
        "events_mapped": totals["mapped"],
        "events_failed": totals["failed"],
        "events_forwarded": totals["forwarded"],
        "throughput_per_second": round(recent_mapped / window, 2),
        "last_event_at": last_event_ms / 1000 if last_event_ms else None,
    }


async def read_pipeline_history(minutes: int) -> list[dict]:
    from app.models.ingestion import PipelineCounterModel

    now = datetime.now(timezone.utc)
    buckets = [minute_bucket(now - timedelta(minutes=i)) for i in range(minutes - 1, -1, -1)]
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PipelineCounterModel.bucket, PipelineCounterModel.name, PipelineCounterModel.value)
            .where(PipelineCounterModel.bucket >= buckets[0], PipelineCounterModel.bucket != "total")
        )).all()
    series = {b: {"minute": b, **{f"events_{n}": 0 for n in COUNTER_NAMES}} for b in buckets}
    for bucket, name, value in rows:
        if bucket in series and name in COUNTER_NAMES:
            series[bucket][f"events_{name}"] = value
    return list(series.values())


async def seed_counters_if_empty() -> None:
    """First run after counters were introduced: start totals from what the DB already records."""
    from app.models.ingestion import PipelineCounterModel
    from app.models.connector import ConnectorModel
    from app.models.forwarder import ForwarderModel
    from app.models.dlq import DLQEventModel

    async with AsyncSessionLocal() as db:
        if await db.get(PipelineCounterModel, "total|received"):
            return
        received = await db.scalar(select(func.coalesce(func.sum(ConnectorModel.events_processed), 0)))
        forwarded = await db.scalar(select(func.coalesce(func.sum(ForwarderModel.events_forwarded), 0)))
        failed = await db.scalar(select(func.count()).select_from(DLQEventModel))
        seed = {"received": received, "failed": failed, "mapped": max(received - failed, 0), "forwarded": forwarded}
        for name, value in seed.items():
            # All 4 workers run this at startup; only the first insert wins
            stmt = _insert(PipelineCounterModel).values(
                id=f"total|{name}", bucket="total", name=name, value=int(value or 0),
            ).on_conflict_do_nothing(index_elements=["id"])
            await db.execute(stmt)
        await db.commit()
        logger.info("Seeded pipeline counters from existing data: %s", seed)
