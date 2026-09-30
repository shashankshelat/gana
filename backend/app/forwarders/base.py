from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ForwarderMeta:
    type_id: str
    display_name: str
    description: str
    icon: str
    category: str  # "siem", "data_lake", "storage", "streaming"
    config_schema: dict = field(default_factory=dict)
    supports_batch: bool = True
    max_batch_size: int = 1000
    # "beta" = built from the vendor's public API docs, not yet verified against a live tenant
    maturity: str = "stable"
    maturity_note: str = ""


def review_fields(key: str, title: str, placeholder: str) -> dict:
    """Config fields that send not-confidently-classified events to a separate place."""
    return {
        key: {"type": "string", "title": title, "placeholder": placeholder},
        "review_include_unverified": {
            "type": "boolean", "title": "Also send events from connectors without per-event routes", "default": False,
        },
    }


def event_mapping_status(event: dict) -> str:
    status = event.get("_mapping_status")
    if status:
        return status
    for label in (event.get("metadata") or {}).get("labels") or []:
        if isinstance(label, str) and label.startswith("gana:mapping="):
            return label.split("=", 1)[1]
    return ""


class BaseForwarder(ABC):
    meta: ForwarderMeta

    def is_review(self, event: dict) -> bool:
        """True when this event should go to the review destination instead of the main one."""
        status = event_mapping_status(event)
        return status == "unclassified" or (status == "unverified" and bool(self.config.get("review_include_unverified")))

    def __init__(self, forwarder_id: str, config: dict):
        self.forwarder_id = forwarder_id
        self.config = config

    @abstractmethod
    async def validate_config(self) -> tuple[bool, str]:
        pass

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        pass

    @abstractmethod
    async def forward(self, events: list[dict]) -> tuple[int, int]:
        """Forward events. Returns (success_count, failed_count)."""
        pass

    def apply_filter(self, events: list[dict], filter_rules: dict) -> list[dict]:
        if not filter_rules:
            return events
        filtered = []
        include_class_uids = filter_rules.get("class_uids", [])
        include_severity_min = filter_rules.get("severity_min", 0)
        exclude_connector_ids = filter_rules.get("exclude_connectors", [])

        for event in events:
            if include_class_uids and event.get("class_uid") not in include_class_uids:
                continue
            if event.get("severity_id", 0) < include_severity_min:
                continue
            if event.get("_connector_id") in exclude_connector_ids:
                continue
            filtered.append(event)
        return filtered
