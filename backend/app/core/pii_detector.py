import hashlib
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Built-in regex patterns
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ipv4": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    "aws_key": re.compile(r"\b(AKIA|ASIA|AROA)[A-Z0-9]{16}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "api_key_generic": re.compile(r"\b[a-zA-Z0-9]{32,64}\b"),
}

# Fields that are excluded from PII scanning (structural OCSF fields)
EXCLUDED_FIELDS = {
    "class_uid", "category_uid", "type_uid", "severity_id", "status_id",
    "time", "metadata", "_connector_id", "_connector_type", "_raw",
}


def _mask_value(value: str, mode: str) -> str:
    if mode == "hash":
        return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]
    if mode == "drop":
        return "[REDACTED]"
    half = len(value) // 2
    return value[:2] + "*" * max(half, 4) + value[-2:] if len(value) > 4 else "****"


def _scan_string(text: str, active_patterns: list[str], mode: str) -> tuple[str, bool]:
    modified = False
    result = text
    for pattern_name in active_patterns:
        pat = PII_PATTERNS.get(pattern_name)
        if not pat:
            continue
        if pat.search(result):
            result = pat.sub(lambda m: _mask_value(m.group(), mode), result)
            modified = True
    return result, modified


def _process_value(val: Any, active_patterns: list[str], mode: str) -> tuple[Any, bool]:
    if isinstance(val, str):
        return _scan_string(val, active_patterns, mode)
    if isinstance(val, dict):
        return _process_dict(val, active_patterns, mode)
    if isinstance(val, list):
        modified = False
        result = []
        for item in val:
            new_item, m = _process_value(item, active_patterns, mode)
            result.append(new_item)
            modified = modified or m
        return result, modified
    return val, False


def _process_dict(d: dict, active_patterns: list[str], mode: str, depth: int = 0) -> tuple[dict, bool]:
    if depth > 10:
        return d, False
    modified = False
    result = {}
    for k, v in d.items():
        if k in EXCLUDED_FIELDS:
            result[k] = v
            continue
        new_v, m = _process_value(v, active_patterns, mode)
        result[k] = new_v
        modified = modified or m
    return result, modified


def detect_and_mask(event: dict, active_patterns: list[str], mode: str = "mask") -> tuple[dict, bool]:
    if not active_patterns:
        return event, False
    result, modified = _process_dict(event, active_patterns, mode)
    return result, modified


def get_available_patterns() -> list[dict]:
    return [
        {"id": "email", "name": "Email Addresses", "example": "user@example.com → us**@ex******.com"},
        {"id": "credit_card", "name": "Credit Card Numbers", "example": "4111111111111111 → 41*************"},
        {"id": "ssn", "name": "Social Security Numbers", "example": "123-45-6789 → 12*-**-****"},
        {"id": "phone", "name": "Phone Numbers", "example": "+1-800-555-1234 → +1-800-5****"},
        {"id": "ipv4", "name": "IPv4 Addresses", "example": "192.168.1.100 → 19***.***.*.***"},
        {"id": "aws_key", "name": "AWS Access Keys", "example": "AKIAIOSFODNN7EXAMPLE → AK**************"},
        {"id": "jwt", "name": "JWT Tokens", "example": "eyJ... → [REDACTED]"},
    ]
