"""Alert, case and email-security platforms as sources (added from Detection-blocks).

Each connector runs a saved search on the platform every poll and ingests the result rows.
Rows are wrapped with a normalized event time, a stable id and the search name, then mapped
to OCSF Detection Finding (2004) by default; the Unmapped Samples page and "Ask AI to fix
mapping" can then add per-type routes for the platform's specific fields.

API shapes come from the Detection-blocks connectors, which were written from each vendor's
public docs — hence every connector here is marked beta."""
import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector

BETA_NOTE = "Built from the vendor's public API docs (via Detection-blocks); not yet verified against a live tenant."

_TIME_FALLBACKS = ("_time", "@timestamp", "timestamp", "time", "created_at", "createdAt", "eventtime", "event_time")


def _get(row: Any, path: str):
    cur = row
    for part in (path or "").split("."):
        if not part:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def _finding_mapping(product: str) -> dict:
    return {
        "_default_class_uid": 2004,
        "activity_id": "$const:1",
        "activity_name": "$const:Create",
        "time": "event_time",
        "metadata.uid": "result_id",
        "metadata.event_code": "search_name",
        "metadata.product.name": f"$const:{product}",
        "metadata.product.vendor_name": f"$const:{product}",
        "finding_info.uid": "result_id",
        "finding_info.title": "search_name",
        "finding_info.product_uid": "result_id",
    }


def _schema(extra: dict, required: list[str], time_field: str, id_field: str, query_hint: str) -> dict:
    return {
        "properties": {
            **extra,
            "query": {"type": "string", "title": "Saved search (runs every poll)", "multiline": True, "placeholder": query_hint},
            "search_name": {"type": "string", "title": "Search name (becomes the finding title)"},
            "time_field": {"type": "string", "title": "Result time field", "default": time_field},
            "id_field": {"type": "string", "title": "Result id field", "default": id_field},
        },
        "required": required + ["query"],
    }


class SavedSearchConnector(BaseConnector):
    """Base for sources that pull results of a saved search from a platform's query API."""

    async def _search(self, query: str, start: datetime, end: datetime) -> list[dict]:
        raise NotImplementedError

    async def validate_config(self) -> tuple[bool, str]:
        missing = [k for k in self.meta.config_schema.get("required", []) if not self.config.get(k)]
        return (False, f"Missing required settings: {', '.join(missing)}") if missing else (True, "")

    def polling_configured(self) -> tuple[bool, str]:
        return (True, "") if self.config.get("query") else (False, "No saved search configured")

    def _field(self, name: str) -> str:
        return self.config.get(name) or self.meta.config_schema["properties"][name].get("default", "")

    def _wrap(self, row: dict) -> dict:
        from app.core.poller import _parse_time_ms
        raw_time = _get(row, self._field("time_field"))
        if raw_time is None:
            raw_time = next((row.get(k) for k in _TIME_FALLBACKS if isinstance(row, dict) and row.get(k) is not None), None)
        ms = _parse_time_ms(raw_time) or int(datetime.now(timezone.utc).timestamp() * 1000)
        rid = _get(row, self._field("id_field"))
        if rid in (None, ""):
            # No id from the platform: a content hash keeps metadata.uid stable across polls
            rid = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
        return {
            "platform": self.meta.display_name,
            "search_name": self.config.get("search_name") or f"{self.meta.display_name} saved search",
            "event_time": datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z",
            "result_id": str(rid),
            "result": row,
        }

    async def fetch_events(self, since: Optional[str] = None) -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=1)
        if since:
            try:
                start = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                pass
        rows = await self._search(self.config["query"], start, end)
        return [self._wrap(r) for r in rows if isinstance(r, dict)]

    async def test_connection(self) -> tuple[bool, str]:
        ok, msg = await self.validate_config()
        if not ok:
            return False, msg
        try:
            end = datetime.now(timezone.utc)
            rows = await self._search(self.config["query"], end - timedelta(hours=1), end)
            return True, f"Connected — the saved search returned {len(rows)} results for the last hour"
        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"


def _hours(start: datetime, end: datetime) -> int:
    return max(1, math.ceil((end - start).total_seconds() / 3600))


@register_connector
class SublimeSecurityConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="sublime_security", display_name="Sublime Security",
        description="Pull email-security results (MQL saved search over message groups) as OCSF Detection Findings",
        icon="sublime", category="email_security", auth_methods=["api_key"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta",
        maturity_note=BETA_NOTE + " The query endpoint path is configurable because it varies by API version.",
        config_schema=_schema({
            "base_url": {"type": "string", "title": "Platform URL", "default": "https://platform.sublime.security"},
            "api_key": {"type": "string", "title": "API Key", "secret": True},
            "query_path": {"type": "string", "title": "Query endpoint path", "default": "/v1/message-groups/query"},
        }, ["api_key"], "created_at", "id", "type.inbound and length(attachments) > 0"),
        default_mapping=_finding_mapping("Sublime Security"),
    )

    async def _search(self, query, start, end):
        base = (self.config.get("base_url") or "https://platform.sublime.security").rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base}{self.config.get('query_path') or '/v1/message-groups/query'}",
                headers={"Authorization": f"Bearer {self.config['api_key']}", "Content-Type": "application/json"},
                json={"query": query, "created_at": {"gte": start.isoformat(), "lte": end.isoformat()}},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("message_groups") or data.get("messages") or data.get("data") or []


@register_connector
class PaloAltoXSOARConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="palo_alto_xsoar", display_name="Palo Alto Cortex XSOAR / XSIAM",
        description="Pull results of an XQL saved search (e.g. the alerts dataset) as OCSF Detection Findings",
        icon="paloalto", category="alerts", auth_methods=["api_key"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta", maturity_note=BETA_NOTE,
        config_schema=_schema({
            "api_url": {"type": "string", "title": "API URL", "placeholder": "https://api-<tenant>.xdr.us.paloaltonetworks.com"},
            "api_key": {"type": "string", "title": "API Key", "secret": True},
            "api_key_id": {"type": "string", "title": "API Key ID"},
        }, ["api_url", "api_key", "api_key_id"], "_time", "alert_id", "dataset = alerts | limit 1000"),
        default_mapping=_finding_mapping("Palo Alto Cortex"),
    )

    async def _search(self, query, start, end):
        base = self.config["api_url"].rstrip("/")
        headers = {"Authorization": self.config["api_key"], "x-xdr-auth-id": str(self.config["api_key_id"]),
                   "Content-Type": "application/json"}
        window_ms = int((end - start).total_seconds() * 1000)
        async with httpx.AsyncClient(timeout=60) as client:
            started = await client.post(f"{base}/public_api/v1/xql/start_xql_query", headers=headers,
                                        json={"request_data": {"query": query, "timeframe": {"relativeTime": window_ms}}})
            started.raise_for_status()
            query_id = started.json()["reply"]
            # XQL runs asynchronously: poll for the result (up to ~2 minutes)
            for _ in range(60):
                res = await client.post(f"{base}/public_api/v1/xql/get_query_results", headers=headers,
                                        json={"request_data": {"query_id": query_id, "pending_flag": False, "format": "json"}})
                res.raise_for_status()
                reply = res.json().get("reply", {})
                if reply.get("status") == "SUCCESS":
                    return reply.get("results", {}).get("data", [])
                if reply.get("status") == "FAIL":
                    raise RuntimeError(reply.get("error", "XQL query failed"))
                await asyncio.sleep(2)
        raise TimeoutError("XQL query timed out waiting for results")


@register_connector
class Rapid7InsightIDRConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="rapid7_insightidr", display_name="Rapid7 InsightIDR",
        description="Pull results of a LEQL Log Search query (one log key) as OCSF Detection Findings",
        icon="rapid7", category="alerts", auth_methods=["api_key"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta", maturity_note=BETA_NOTE,
        config_schema=_schema({
            "region": {"type": "string", "title": "Region", "default": "us", "enum": ["us", "us2", "us3", "eu", "ca", "au", "ap"]},
            "api_key": {"type": "string", "title": "API Key", "secret": True},
            "log_key": {"type": "string", "title": "Log Key"},
        }, ["api_key", "log_key"], "timestamp", "sequence_number_str", "where(action=FAILED_LOGIN)"),
        default_mapping=_finding_mapping("Rapid7 InsightIDR"),
    )

    async def _search(self, query, start, end):
        region = self.config.get("region") or "us"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"https://{region}.api.insight.rapid7.com/log_search/query/logs/{self.config['log_key']}",
                headers={"X-Api-Key": self.config["api_key"], "Accept": "application/json"},
                params={"query": query, "from": int(start.timestamp() * 1000), "to": int(end.timestamp() * 1000)},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("events", data.get("logs", []))


@register_connector
class ExabeamConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="exabeam", display_name="Exabeam",
        description="Pull results of an Exabeam Search API query as OCSF Detection Findings",
        icon="exabeam", category="alerts", auth_methods=["oauth2"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta",
        maturity_note=BETA_NOTE + " Medium confidence on the search endpoint shape.",
        config_schema=_schema({
            "base_url": {"type": "string", "title": "API Base URL", "placeholder": "https://api.us-west.exabeam.cloud"},
            "client_id": {"type": "string", "title": "Client ID"},
            "client_secret": {"type": "string", "title": "Client Secret", "secret": True},
        }, ["base_url", "client_id", "client_secret"], "approxLogTime", "id", 'activity_type:"authentication" AND outcome:"fail"'),
        default_mapping=_finding_mapping("Exabeam"),
    )

    async def _search(self, query, start, end):
        base = self.config["base_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            tok = await client.post(f"{base}/auth/v1/token", json={
                "client_id": self.config["client_id"], "client_secret": self.config["client_secret"],
                "grant_type": "client_credentials"})
            tok.raise_for_status()
            resp = await client.post(
                f"{base}/search/v2/events",
                headers={"Authorization": f"Bearer {tok.json()['access_token']}", "Content-Type": "application/json"},
                json={"query": query, "startTime": start.isoformat(), "endTime": end.isoformat(), "limit": 1000},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("events", data.get("rows", []))


@register_connector
class SecuronixConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="securonix", display_name="Securonix",
        description="Pull results of a Spotter search as OCSF Detection Findings",
        icon="securonix", category="alerts", auth_methods=["basic"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta", maturity_note=BETA_NOTE,
        config_schema=_schema({
            "url": {"type": "string", "title": "Tenant URL", "placeholder": "https://acme.securonix.net"},
            "username": {"type": "string", "title": "Username"},
            "password": {"type": "string", "title": "Password", "secret": True},
        }, ["url", "username", "password"], "eventtime", "eventid", "index = violation"),
        default_mapping=_finding_mapping("Securonix"),
    )

    async def _search(self, query, start, end):
        base = self.config["url"].rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            tok = await client.get(f"{base}/Snypr/ws/token/generate",
                                   params={"username": self.config["username"], "password": self.config["password"]})
            tok.raise_for_status()
            token = tok.text.strip().strip('"')
            resp = await client.get(f"{base}/Snypr/ws/spotter/search", headers={"Authorization": f"Bearer {token}"},
                                    params={"query": query, "timeperiod": f"Last {_hours(start, end)} Hours"})
            resp.raise_for_status()
            data = resp.json()
        return data.get("events", data.get("result", []))


@register_connector
class HuntersConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="hunters", display_name="Hunters",
        description="Pull Hunters leads/search results as OCSF Detection Findings",
        icon="hunters", category="alerts", auth_methods=["api_key"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta",
        maturity_note=BETA_NOTE + " Medium-low confidence on exact query semantics.",
        config_schema=_schema({
            "base_url": {"type": "string", "title": "API Base URL"},
            "api_token": {"type": "string", "title": "API Token", "secret": True},
        }, ["base_url", "api_token"], "created_at", "id", "severity:high"),
        default_mapping=_finding_mapping("Hunters"),
    )

    async def _search(self, query, start, end):
        base = self.config["base_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base}/api/search",
                                     headers={"Authorization": f"Bearer {self.config['api_token']}", "Content-Type": "application/json"},
                                     json={"query": query, "time_range_hours": _hours(start, end)})
            resp.raise_for_status()
            data = resp.json()
        return data.get("results", data.get("leads", []))


@register_connector
class GuruculConnector(SavedSearchConnector):
    meta = ConnectorMeta(
        type_id="gurucul", display_name="Gurucul",
        description="Pull results of a Gurucul query as OCSF Detection Findings (fully configurable endpoint)",
        icon="gurucul", category="alerts", auth_methods=["api_key"], supports_polling=True,
        default_ocsf_class_uid=2004, maturity="beta",
        maturity_note="Lowest confidence: little of Gurucul's query API is public, so the endpoint path is configurable.",
        config_schema=_schema({
            "base_url": {"type": "string", "title": "API Base URL"},
            "api_token": {"type": "string", "title": "API Token", "secret": True},
            "query_path": {"type": "string", "title": "Query endpoint path", "default": "/api/search"},
        }, ["base_url", "api_token"], "timestamp", "id", "riskScore > 80"),
        default_mapping=_finding_mapping("Gurucul"),
    )

    async def _search(self, query, start, end):
        base = self.config["base_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base}{self.config.get('query_path') or '/api/search'}",
                                     headers={"Authorization": f"Bearer {self.config['api_token']}", "Content-Type": "application/json"},
                                     json={"query": query, "timeRangeHours": _hours(start, end)})
            resp.raise_for_status()
            data = resp.json()
        return data.get("results", data.get("data", []))
