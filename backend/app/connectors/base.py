from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConnectorMeta:
    type_id: str
    display_name: str
    description: str
    icon: str
    category: str  # "cloud", "security", "productivity", "network", "generic"
    auth_methods: list[str]  # "api_key", "oauth2", "webhook", "basic", "certificate"
    supports_webhook: bool = False
    supports_polling: bool = False
    supports_streaming: bool = False
    default_ocsf_class_uid: int = 3002  # API Activity
    config_schema: dict = field(default_factory=dict)
    default_mapping: dict = field(default_factory=dict)
    # "beta" = built from the vendor's public API docs, not yet verified against a live tenant
    maturity: str = "stable"
    maturity_note: str = ""


class BaseConnector(ABC):
    meta: ConnectorMeta

    def __init__(self, connector_id: str, config: dict, mapping_rules: dict):
        self.connector_id = connector_id
        self.config = config
        self.mapping_rules = mapping_rules

    @abstractmethod
    async def validate_config(self) -> tuple[bool, str]:
        """Validate connector configuration. Returns (is_valid, error_message)."""
        pass

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Test connectivity. Returns (success, message)."""
        pass

    async def fetch_events(self, since: Optional[str] = None) -> list[dict]:
        """Poll-based connectors implement this."""
        return []

    def polling_configured(self) -> tuple[bool, str]:
        """Whether this connector's config allows polling; connectors with optional polling override this."""
        return True, ""

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        """Webhook-based connectors implement this."""
        return [payload]

    def get_webhook_path(self) -> str:
        return f"/webhooks/{self.meta.type_id}/{self.connector_id}"

    def normalize_timestamp(self, ts: Any) -> int:
        """Convert any timestamp to OCSF epoch_ms."""
        import time
        from datetime import datetime, timezone

        if isinstance(ts, int):
            if ts > 1e12:
                return ts
            return int(ts * 1000)
        if isinstance(ts, float):
            return int(ts * 1000)
        if isinstance(ts, str):
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
            ]:
                try:
                    dt = datetime.strptime(ts, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    continue
        return int(time.time() * 1000)

    def get_nested(self, data: dict, path: str, default=None):
        """Get value from nested dict using dot notation."""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current

    def apply_mapping(self, raw_event: dict) -> dict:
        """Apply connector's mapping rules to produce partial OCSF event."""
        mapped = {}
        for ocsf_field, source_path in self.mapping_rules.items():
            if isinstance(source_path, str) and source_path.startswith("$const:"):
                mapped[ocsf_field] = source_path[7:]
            elif isinstance(source_path, str):
                value = self.get_nested(raw_event, source_path)
                if value is not None:
                    self._set_nested(mapped, ocsf_field, value)
            elif isinstance(source_path, dict):
                if "path" in source_path:
                    value = self.get_nested(raw_event, source_path["path"])
                    if value is not None and "transform" in source_path:
                        value = self._apply_transform(value, source_path["transform"])
                    if value is not None:
                        self._set_nested(mapped, ocsf_field, value)
        return mapped

    def _set_nested(self, data: dict, path: str, value: Any):
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def _apply_transform(self, value: Any, transform: str) -> Any:
        transforms = {
            "lower": lambda v: v.lower() if isinstance(v, str) else v,
            "upper": lambda v: v.upper() if isinstance(v, str) else v,
            "int": lambda v: int(v) if v is not None else None,
            "str": lambda v: str(v) if v is not None else None,
            "bool": lambda v: bool(v),
        }
        fn = transforms.get(transform)
        return fn(value) if fn else value
