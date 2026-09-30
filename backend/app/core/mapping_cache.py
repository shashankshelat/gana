import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Each uvicorn worker has its own cache, but connectors are edited through whichever worker
# serves the request — so refresh periodically and read through to the DB on a miss.
_REFRESH_SECONDS = 15


class MappingCache:
    """
    In-memory store of connector_id → {ocsf_class_uid, mapping_rules}.
    Loaded once at startup from the DB; updated on connector save or approval.
    Pipeline workers do a single dict lookup instead of reading rules from every Kafka message.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}
        # connector_ids with an AI suggestion already in flight — avoids duplicate AI calls
        self._pending_ai: set[str] = set()
        self._loaded_at = 0.0

    async def load(self):
        from app.core.database import AsyncSessionLocal
        from app.models.connector import ConnectorModel
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ConnectorModel))
            # Rebuild rather than merge so connectors deleted via another worker drop out
            self._cache = {
                c.id: {
                    "ocsf_class_uid": 3002 if c.ocsf_class_uid is None else c.ocsf_class_uid,
                    "mapping_rules": c.mapping_rules or {},
                }
                for c in result.scalars().all()
            }
        self._loaded_at = time.time()
        logger.debug("Mapping cache loaded: %d connectors", len(self._cache))

    async def refresh_if_stale(self):
        if time.time() - self._loaded_at > _REFRESH_SECONDS:
            await self.load()

    async def get_or_load(self, connector_id: str) -> Optional[dict]:
        cached = self._cache.get(connector_id)
        if (cached is None or not cached.get("mapping_rules")) and time.time() - self._loaded_at > 1:
            # Likely created or given rules through another worker since our last refresh
            await self.load()
            cached = self._cache.get(connector_id)
        return cached

    def get(self, connector_id: str) -> Optional[dict]:
        return self._cache.get(connector_id)

    def update(self, connector_id: str, mapping_rules: dict, ocsf_class_uid: int = 3002):
        self._cache[connector_id] = {
            "ocsf_class_uid": ocsf_class_uid,
            "mapping_rules": mapping_rules,
        }
        self._pending_ai.discard(connector_id)
        logger.info("Mapping cache updated for connector_id=%s", connector_id)

    def invalidate(self, connector_id: str):
        self._cache.pop(connector_id, None)
        self._pending_ai.discard(connector_id)

    def is_pending_ai(self, connector_id: str) -> bool:
        return connector_id in self._pending_ai

    def mark_pending_ai(self, connector_id: str):
        self._pending_ai.add(connector_id)

    def clear_pending_ai(self, connector_id: str):
        self._pending_ai.discard(connector_id)


mapping_cache = MappingCache()
