"""Shared helpers for forwarders: event shaping, batching, and cloud auth."""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.forwarders.base import BaseForwarder

logger = logging.getLogger(__name__)

BETA_NOTE = "Built from the vendor's public API docs; not yet verified against a live tenant."


def clean_event(event: dict) -> dict:
    """The OCSF event without pipeline-internal fields (_raw, _connector_id, ...)."""
    return {k: v for k, v in event.items() if not k.startswith("_")}


def event_time_ms(event: dict) -> int:
    t = event.get("time")
    return int(t) if isinstance(t, (int, float)) and t > 0 else int(time.time() * 1000)


def event_time_iso(event: dict) -> str:
    return datetime.fromtimestamp(event_time_ms(event) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def event_summary(event: dict) -> str:
    """A one-line human summary for platforms that want a message string."""
    return event.get("message") or " · ".join(
        str(p) for p in (event.get("class_name"), event.get("activity_name"), event.get("status")) if p
    ) or "OCSF event"


def flatten(data: Any, prefix: str = "", sep: str = "_", out: dict | None = None) -> dict:
    """Flat key/value view of a nested event, for formats without nesting (GELF, CEF, LEEF)."""
    if out is None:
        out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            flatten(v, f"{prefix}{sep}{k}" if prefix else str(k), sep, out)
    elif isinstance(data, list):
        out[prefix] = json.dumps(data, default=str)
    elif data is not None:
        out[prefix] = data
    return out


def chunks(items: list, size: int):
    for i in range(0, len(items), max(1, size)):
        yield items[i:i + size]


class HttpBatchForwarder(BaseForwarder):
    """Base for HTTP ingestion APIs: subclasses build one request per batch.

    Subclasses implement `_request(batch) -> dict` returning httpx.request kwargs
    (method, url, headers, json/content, auth) and may override `_ok`."""

    ok_statuses = (200, 201, 202, 204)
    timeout = 30

    async def validate_config(self) -> tuple[bool, str]:
        missing = [k for k in self.meta.config_schema.get("required", []) if not self.config.get(k)]
        return (False, f"Missing required settings: {', '.join(missing)}") if missing else (True, "")

    async def test_connection(self) -> tuple[bool, str]:
        ok, msg = await self.validate_config()
        if not ok:
            return False, msg
        test = {"class_uid": 0, "class_name": "Base Event", "message": "GANA connection test",
                "time": int(time.time() * 1000), "metadata": {"product": {"name": "GANA"}}}
        try:
            self.last_error = ""
            success, _ = await self.forward([test])
            if success:
                return True, f"Test event accepted by {self.meta.display_name}"
            return False, self.last_error or "The platform rejected the test event"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def _ok(self, resp: httpx.Response) -> bool:
        return resp.status_code in self.ok_statuses

    async def _request(self, batch: list[dict]) -> dict:
        raise NotImplementedError

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        batch_size = int(self.config.get("batch_size") or self.meta.max_batch_size or 100)
        success = failed = 0
        self.last_error = ""
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.config.get("verify_ssl", True)) as client:
            for batch in chunks([clean_event(e) for e in events], batch_size):
                try:
                    kwargs = await self._request(batch)
                    resp = await client.request(**kwargs)
                    if self._ok(resp):
                        success += len(batch)
                    else:
                        failed += len(batch)
                        self.last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                        logger.error("%s forwarder %s: %s", self.meta.type_id, self.forwarder_id, self.last_error)
                except Exception as e:
                    failed += len(batch)
                    self.last_error = f"{type(e).__name__}: {e}"
                    logger.error("%s forwarder %s: %s", self.meta.type_id, self.forwarder_id, self.last_error)
        return success, failed


# ── Cloud auth ────────────────────────────────────────────────────────────────

_token_cache: dict[str, tuple[str, float]] = {}


async def google_sa_token(service_account_json: str, scope: str) -> str:
    """OAuth access token for a Google service account (JWT bearer grant)."""
    import jwt as pyjwt

    sa = json.loads(service_account_json)
    key = f"google|{sa.get('client_email')}|{scope}"
    cached = _token_cache.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    now = int(time.time())
    assertion = pyjwt.encode(
        {"iss": sa["client_email"], "scope": scope, "aud": "https://oauth2.googleapis.com/token",
         "iat": now, "exp": now + 3600},
        sa["private_key"], algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        resp.raise_for_status()
        data = resp.json()
    _token_cache[key] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
    return data["access_token"]


async def azure_ad_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    """OAuth access token for an Entra ID app registration (client credentials)."""
    key = f"azure|{tenant_id}|{client_id}|{scope}"
    cached = _token_cache.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials", "client_id": client_id,
                  "client_secret": client_secret, "scope": scope},
        )
        resp.raise_for_status()
        data = resp.json()
    _token_cache[key] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
    return data["access_token"]
