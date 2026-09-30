import time
import uuid
import logging
from typing import Any, Optional

from app.core.schema_manager import schema_manager

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    "informational": 1, "information": 1, "info": 1, "low": 2,
    "medium": 3, "high": 4, "critical": 5, "fatal": 5,
    "warn": 3, "warning": 3, "error": 4,
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}

STATUS_MAP = {
    "success": 1, "ok": 1, "200": 1,
    "failure": 2, "fail": 2, "error": 2, "failed": 2,
    "allow": 1, "deny": 2, "challenge": 99, "unknown": 0,
}

OCSF_CLASS_NAMES = {
    0: "Base Event",
    1001: "File System Activity",
    1002: "Kernel Extension Activity",
    1003: "Kernel Activity",
    1004: "Memory Activity",
    1005: "Module Activity",
    1006: "Scheduled Job Activity",
    1007: "Process Activity",
    2001: "Security Finding",
    2002: "Vulnerability Finding",
    2003: "Compliance Finding",
    2004: "Detection Finding",
    3001: "Account Change",
    3002: "Authentication",
    3003: "Authorize Session",
    3004: "Entity Management",
    3005: "User Access Management",
    3006: "Group Management",
    4001: "Network Activity",
    4002: "HTTP Activity",
    4003: "DNS Activity",
    4004: "DHCP Activity",
    4005: "RDP Activity",
    4006: "SMB Activity",
    4007: "SSH Activity",
    4008: "FTP Activity",
    5001: "Inventory Info",
    5002: "Config State",
    5003: "User Inventory Info",
    6001: "Web Resource Activity",
    6002: "Application Lifecycle",
    6003: "API Activity",
    6004: "Web Resource Access Activity",
    6005: "Datastore Activity",
    6006: "File Hosting Activity",
}


MAPPING_LABEL = "gana:mapping="


def mapping_status(mapping_rules: dict, route: dict | None, class_uid: int) -> str:
    """How confidently an event was classified:
    classified   — a per-event-type route matched
    unclassified — the connector has routes but none matched, or the event is a Base Event (0)
    unverified   — the connector has no per-event routes, so its single class was never checked per event"""
    if route and class_uid != 0:
        return "classified"
    if class_uid == 0 or (mapping_rules or {}).get("_routes"):
        return "unclassified"
    return "unverified"


def stamp_mapping_status(event: dict, status: str) -> None:
    """Record the status as an OCSF metadata label (searchable everywhere) and an internal routing hint."""
    meta = event.setdefault("metadata", {})
    labels = [l for l in (meta.get("labels") or []) if not (isinstance(l, str) and l.startswith(MAPPING_LABEL))]
    meta["labels"] = labels + [f"{MAPPING_LABEL}{status}"]
    event["_mapping_status"] = status


class OCSFMapper:
    def map_event(
        self,
        raw_event: dict,
        connector_id: str,
        connector_type: str,
        mapping_rules: dict,
        ocsf_class_uid: int = 3002,
    ) -> dict:
        # Per-event-type routes pick the OCSF class and field mapping; unmatched events use the flat rules
        route = self.match_route(raw_event, mapping_rules)
        if route:
            ocsf_class_uid = int(route.get("class_uid", ocsf_class_uid))
            mapping_rules = route.get("mapping", {})
        elif isinstance((mapping_rules or {}).get("_default_class_uid"), int):
            ocsf_class_uid = mapping_rules["_default_class_uid"]

        ocsf_event = {
            "class_uid": ocsf_class_uid,
            "class_name": OCSF_CLASS_NAMES.get(ocsf_class_uid, "Unknown"),
            "category_uid": ocsf_class_uid // 1000,
            "category_name": self._get_category_name(ocsf_class_uid),
            "type_uid": ocsf_class_uid * 100,
            "time": int(time.time() * 1000),
            "severity_id": 1,
            "severity": "Informational",
            "status_id": 0,
            "metadata": {
                **schema_manager.build_event_metadata(),
                "uid": str(uuid.uuid4()),
                "log_name": connector_type,
                "log_provider": connector_type,
                "logged_time": int(time.time() * 1000),
                "original_time": raw_event.get("time") or raw_event.get("timestamp") or raw_event.get("created_at"),
            },
            "_connector_id": connector_id,
            "_connector_type": connector_type,
            "_raw": raw_event,
        }

        for ocsf_path, source in mapping_rules.items():
            if ocsf_path.startswith("_"):
                continue
            value = self._resolve_value(raw_event, source)
            if value is not None:
                self._set_path(ocsf_event, ocsf_path, value)

        self._normalize_severity(ocsf_event)
        self._normalize_status(ocsf_event)
        self._normalize_time(ocsf_event, raw_event)
        self._normalize_activity(ocsf_event)

        return ocsf_event

    def match_route(self, raw_event: dict, mapping_rules: dict) -> dict | None:
        """First route in mapping_rules["_routes"] whose `when` condition matches the raw event.

        Route shape: {"name", "when": {"field", ...conditions}, "class_uid", "mapping": {ocsf_path: source}}.
        Conditions (every one given must hold): "equals": v, "in": [...], "prefix": [...], "suffix": [...]."""
        for route in (mapping_rules or {}).get("_routes") or []:
            cond = route.get("when") or {}
            value = self._get_path(raw_event, cond.get("field", ""))
            if value is None:
                continue
            checks = []
            if "equals" in cond:
                checks.append(value == cond["equals"])
            if "in" in cond:
                checks.append(value in cond["in"])
            if "prefix" in cond:
                checks.append(isinstance(value, str) and any(value.startswith(p) for p in cond["prefix"]))
            if "suffix" in cond:
                checks.append(isinstance(value, str) and any(value.endswith(x) for x in cond["suffix"]))
            if checks and all(checks):
                return route
        return None

    def _normalize_activity(self, event: dict):
        # Constants arrive as strings ("$const:6"); OCSF ids are integers, and type_uid = class_uid * 100 + activity_id
        activity = event.get("activity_id")
        if isinstance(activity, str) and activity.lstrip("-").isdigit():
            activity = int(activity)
            event["activity_id"] = activity
        if isinstance(activity, int):
            event["type_uid"] = event["class_uid"] * 100 + activity

    def _resolve_value(self, raw: dict, source: Any) -> Any:
        if isinstance(source, str):
            if source.startswith("$const:"):
                const = source[7:]
                return {"true": True, "false": False}.get(const, const)
            return self._get_path(raw, source)
        if isinstance(source, dict):
            path = source.get("path", "")
            value = self._get_path(raw, path)
            if value is not None and "transform" in source:
                value = self._apply_transform(value, source["transform"])
            return value
        return source

    def _get_path(self, data: dict, path: str) -> Any:
        if not path:
            return None
        parts = path.split(".")
        current = data
        for part in parts:
            if "[" in part:
                key, sel = part.split("[", 1)
                sel = sel.rstrip("]")
                current = current.get(key) if isinstance(current, dict) else None
                if not isinstance(current, list):
                    return None
                if "=" in sel:
                    attr, want = sel.split("=", 1)
                    current = next((x for x in current if isinstance(x, dict) and str(x.get(attr)) == want), None)
                elif sel.isdigit() and len(current) > int(sel):
                    current = current[int(sel)]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _set_path(self, data: dict, path: str, value: Any):
        parts = path.split(".")
        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def _apply_transform(self, value: Any, transform: str) -> Any:
        transforms = {
            "lower": lambda v: str(v).lower(),
            "upper": lambda v: str(v).upper(),
            "int": lambda v: int(v) if v is not None else None,
            "str": lambda v: str(v),
            "bool": lambda v: bool(v),
            "epoch_ms": lambda v: int(float(v) * 1000),
            "list": lambda v: v if isinstance(v, list) else [v],
        }
        fn = transforms.get(transform)
        return fn(value) if fn else value

    def _normalize_severity(self, event: dict):
        severity_raw = event.get("severity_id")
        if isinstance(severity_raw, str):
            sid = SEVERITY_MAP.get(severity_raw.lower(), 1)
            event["severity_id"] = sid
        elif isinstance(severity_raw, int):
            event["severity_id"] = max(0, min(6, severity_raw))
        else:
            event["severity_id"] = 1

        severity_labels = {0: "Unknown", 1: "Informational", 2: "Low", 3: "Medium", 4: "High", 5: "Critical", 6: "Fatal"}
        event["severity"] = severity_labels.get(event["severity_id"], "Informational")

    def _normalize_status(self, event: dict):
        status_raw = event.get("status_id")
        if isinstance(status_raw, str):
            event["status_id"] = STATUS_MAP.get(status_raw.lower(), 0)
        elif isinstance(status_raw, int):
            event["status_id"] = status_raw if status_raw in (0, 1, 2, 99) else 0
        else:
            event["status_id"] = 0

        status_labels = {0: "Unknown", 1: "Success", 2: "Failure", 99: "Other"}
        event["status"] = status_labels.get(event["status_id"], "Unknown")

    def _normalize_time(self, event: dict, raw: dict):
        raw_time = event.get("time")
        if isinstance(raw_time, str):
            from app.connectors.base import BaseConnector
            # normalize_timestamp doesn't use self; BaseConnector is abstract and can't be instantiated
            event["time"] = BaseConnector.normalize_timestamp(None, raw_time)
        elif raw_time is None:
            event["time"] = int(time.time() * 1000)

    def _get_category_name(self, class_uid: int) -> str:
        categories = {
            0: "Uncategorized",
            1: "System Activity",
            2: "Findings",
            3: "Identity & Access Management",
            4: "Network Activity",
            5: "Discovery",
            6: "Application Activity",
        }
        return categories.get(class_uid // 1000, "Other")


ocsf_mapper = OCSFMapper()
