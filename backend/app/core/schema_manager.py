import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from packaging import version

from app.core.config import settings

logger = logging.getLogger(__name__)

_schema_cache: Optional[dict] = None
_schema_version: Optional[str] = None
_class_attr_cache: dict[int, list[str]] = {}


class OCSFSchemaManager:
    def __init__(self):
        self.schema_dir = Path(settings.ocsf_schema_dir)
        self.schema_dir.mkdir(parents=True, exist_ok=True)
        self.schema_file = self.schema_dir / "schema.json"
        self.version_file = self.schema_dir / "version.json"
        self.classes_file = self.schema_dir / "classes.json"

    async def get_current_version(self) -> Optional[str]:
        if self.version_file.exists():
            data = json.loads(self.version_file.read_text())
            return data.get("version")
        return None

    async def fetch_latest_release_info(self) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(
                    settings.ocsf_github_api,
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.error("Failed to fetch OCSF release info: %s", e)
        return None

    async def fetch_schema_from_api(self) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.get(settings.ocsf_schema_api)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.error("Failed to fetch OCSF schema from API: %s", e)
        return None

    async def fetch_ocsf_classes(self) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.get("https://schema.ocsf.io/api/classes")
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.error("Failed to fetch OCSF classes: %s", e)
        return None

    async def update_schema(self, force: bool = False) -> dict:
        release_info = await self.fetch_latest_release_info()
        latest_version = None
        if release_info:
            latest_version = release_info.get("tag_name", "").lstrip("v")

        current_version = await self.get_current_version()

        needs_update = force or (
            latest_version
            and (
                not current_version
                or self._version_is_newer(latest_version, current_version)
            )
        )

        if not needs_update and self.schema_file.exists():
            logger.info("OCSF schema is up to date (version %s)", current_version)
            return {"status": "up_to_date", "version": current_version}

        logger.info("Fetching OCSF schema (latest: %s, current: %s)", latest_version, current_version)

        schema_data = await self.fetch_schema_from_api()
        classes_data = await self.fetch_ocsf_classes()

        if schema_data:
            self.schema_file.write_text(json.dumps(schema_data, indent=2))

        if classes_data:
            self.classes_file.write_text(json.dumps(classes_data, indent=2))

        version_info = {
            "version": latest_version or "unknown",
            "updated_at": datetime.utcnow().isoformat(),
            "release_url": release_info.get("html_url") if release_info else None,
            "release_notes": release_info.get("body", "")[:500] if release_info else None,
        }
        self.version_file.write_text(json.dumps(version_info, indent=2))

        global _schema_cache, _schema_version
        _schema_cache = None
        _schema_version = None

        return {
            "status": "updated",
            "version": latest_version,
            "previous_version": current_version,
        }

    def _version_is_newer(self, new: str, current: str) -> bool:
        try:
            return version.parse(new) > version.parse(current)
        except Exception:
            return new != current

    def get_schema(self) -> Optional[dict]:
        global _schema_cache
        if _schema_cache is None and self.schema_file.exists():
            _schema_cache = json.loads(self.schema_file.read_text())
        return _schema_cache

    def get_classes(self) -> Optional[dict]:
        if self.classes_file.exists():
            return json.loads(self.classes_file.read_text())
        return None

    def get_version_info(self) -> Optional[dict]:
        if self.version_file.exists():
            return json.loads(self.version_file.read_text())
        return None

    def _iter_classes(self) -> list[dict]:
        # classes.json from /api/classes is a list; older files may be a dict keyed by name
        classes = self.get_classes() or []
        items = classes.values() if isinstance(classes, dict) else classes
        return [c for c in items if isinstance(c, dict)]

    def get_ocsf_class_fields(self, class_uid: int) -> list[str]:
        """Attribute names for a class, from the cache filled by get_class_attributes (sync callers)."""
        if class_uid in _class_attr_cache:
            return _class_attr_cache[class_uid]
        cached = self.schema_dir / f"class_{class_uid}.json"
        if cached.exists():
            _class_attr_cache[class_uid] = json.loads(cached.read_text())
            return _class_attr_cache[class_uid]
        return []

    async def get_class_attributes(self, class_uid: int) -> list[str]:
        """Attribute names for a class. classes.json has no attributes, so fetch the class once and cache it."""
        fields = self.get_ocsf_class_fields(class_uid)
        if fields:
            return fields
        name = next((c.get("name") for c in self._iter_classes() if c.get("uid") == class_uid), None)
        if not name:
            return []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"https://schema.ocsf.io/api/classes/{name}")
                resp.raise_for_status()
                attrs = resp.json().get("attributes") or {}
        except Exception as e:
            logger.warning("Could not fetch OCSF attributes for class %s: %s", class_uid, e)
            return []
        fields = list(attrs.keys()) if isinstance(attrs, dict) else [
            next(iter(a)) for a in attrs if isinstance(a, dict) and a
        ]
        _class_attr_cache[class_uid] = fields
        (self.schema_dir / f"class_{class_uid}.json").write_text(json.dumps(fields))
        return fields

    def validate_event(self, event: dict) -> tuple[bool, list[str]]:
        classes = self.get_classes()
        if not classes:
            return True, []

        class_uid = event.get("class_uid")
        if not class_uid:
            return False, ["Missing required field: class_uid"]

        errors = []
        required_fields = ["class_uid", "category_uid", "type_uid", "time", "severity_id"]
        for field in required_fields:
            if field not in event:
                errors.append(f"Missing required field: {field}")

        return len(errors) == 0, errors

    def build_event_metadata(self) -> dict:
        version_info = self.get_version_info()
        return {
            "version": version_info.get("version", "1.0.0") if version_info else "1.0.0",
            "product": {
                "name": "GANA",
                "vendor_name": "GANA",
                "version": "1.0.0",
            },
        }


schema_manager = OCSFSchemaManager()
