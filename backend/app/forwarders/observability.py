"""Observability and log-platform destinations (added from Detection-blocks' connector list).

Each sends OCSF events through the platform's own log ingestion API. The OCSF event is kept
intact under one attribute where the platform reserves top-level names (e.g. Datadog "status")."""
import asyncio
import json
import time

import httpx

from app.forwarders._common import (
    BETA_NOTE, HttpBatchForwarder, chunks, clean_event, event_summary, event_time_iso, event_time_ms, flatten,
)
from app.forwarders.base import ForwarderMeta, event_mapping_status
from app.forwarders.registry import register_forwarder

_SEVERITY_WORD = {0: "unknown", 1: "info", 2: "low", 3: "medium", 4: "high", 5: "critical", 6: "fatal"}


@register_forwarder
class DatadogForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="datadog", display_name="Datadog",
        description="Send OCSF events to Datadog Logs via the HTTP intake API (v2)",
        icon="datadog", category="observability", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "api_key": {"type": "string", "title": "API Key", "secret": True},
                "site": {"type": "string", "title": "Site", "default": "datadoghq.com",
                         "enum": ["datadoghq.com", "us3.datadoghq.com", "us5.datadoghq.com", "datadoghq.eu", "ap1.datadoghq.com", "ddog-gov.com"]},
                "service": {"type": "string", "title": "Service", "default": "gana"},
                "tags": {"type": "string", "title": "Tags (comma-separated)", "default": "source:ocsf"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["api_key"],
        },
    )

    async def _request(self, batch):
        site = self.config.get("site") or "datadoghq.com"
        return {
            "method": "POST",
            "url": f"https://http-intake.logs.{site}/api/v2/logs",
            "headers": {"DD-API-KEY": self.config["api_key"], "Content-Type": "application/json"},
            # OCSF nested under "ocsf": Datadog reserves top-level attributes like status and service
            "json": [{
                "ddsource": "ocsf", "service": self.config.get("service") or "gana",
                "ddtags": f'{self.config.get("tags") or "source:ocsf"},gana_mapping:{event_mapping_status(e) or "unknown"}',
                "hostname": "gana",
                "message": event_summary(e), "ocsf": e,
            } for e in batch],
        }


@register_forwarder
class NewRelicForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="new_relic", display_name="New Relic",
        description="Send OCSF events to New Relic Logs via the Log API",
        icon="newrelic", category="observability", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "license_key": {"type": "string", "title": "License / Ingest Key", "secret": True},
                "region": {"type": "string", "title": "Region", "default": "US", "enum": ["US", "EU"]},
                "log_type": {"type": "string", "title": "logtype attribute", "default": "ocsf"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["license_key"],
        },
    )

    async def _request(self, batch):
        host = "log-api.eu.newrelic.com" if self.config.get("region") == "EU" else "log-api.newrelic.com"
        return {
            "method": "POST",
            "url": f"https://{host}/log/v1",
            "headers": {"Api-Key": self.config["license_key"], "Content-Type": "application/json"},
            "json": [{
                "common": {"attributes": {"logtype": self.config.get("log_type") or "ocsf", "service": "gana"}},
                "logs": [{"timestamp": event_time_ms(e), "message": event_summary(e), "attributes": {"ocsf": e}}
                         for e in batch],
            }],
        }


@register_forwarder
class GrafanaLokiForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="grafana_loki", display_name="Grafana Loki / Grafana Cloud Logs",
        description="Push OCSF events to Loki (self-hosted or Grafana Cloud) via /loki/api/v1/push",
        icon="grafana", category="observability", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "Loki URL", "placeholder": "https://logs-prod-006.grafana.net"},
                "username": {"type": "string", "title": "Username / Grafana Cloud user ID"},
                "password": {"type": "string", "title": "Password / API token", "secret": True},
                "tenant_id": {"type": "string", "title": "Tenant (X-Scope-OrgID, self-hosted multi-tenant)"},
                "job_label": {"type": "string", "title": "job label", "default": "gana"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["url"],
        },
    )

    async def _request(self, batch):
        # One stream per OCSF class keeps label cardinality low and queries fast
        streams: dict[tuple[str, str], list] = {}
        for e in batch:
            key = (str(e.get("class_name") or "Base Event"), event_mapping_status(e) or "unknown")
            streams.setdefault(key, []).append(
                [str(event_time_ms(e) * 1_000_000), json.dumps(e, default=str)])
        headers = {"Content-Type": "application/json"}
        if self.config.get("tenant_id"):
            headers["X-Scope-OrgID"] = self.config["tenant_id"]
        req = {
            "method": "POST",
            "url": f"{self.config['url'].rstrip('/')}/loki/api/v1/push",
            "headers": headers,
            "json": {"streams": [
                {"stream": {"job": self.config.get("job_label") or "gana", "ocsf_class": cls, "mapping": status}, "values": values}
                for (cls, status), values in streams.items()
            ]},
        }
        if self.config.get("username"):
            req["auth"] = (self.config["username"], self.config.get("password", ""))
        return req


@register_forwarder
class GraylogForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="graylog", display_name="Graylog",
        description="Send OCSF events to a Graylog GELF HTTP input (one message per request)",
        icon="graylog", category="siem", max_batch_size=200, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "GELF HTTP input URL", "placeholder": "http://graylog:12201"},
                "host_field": {"type": "string", "title": "host field", "default": "gana"},
                "concurrency": {"type": "integer", "title": "Parallel requests", "default": 8},
            },
            "required": ["url"],
        },
    )

    def _gelf(self, e: dict) -> dict:
        msg = {"version": "1.1", "host": self.config.get("host_field") or "gana",
               "short_message": event_summary(e), "timestamp": event_time_ms(e) / 1000,
               "full_message": json.dumps(e, default=str)}
        # GELF additional fields must be flat and prefixed with "_" ("_id" is reserved)
        for k, v in flatten(e).items():
            if k != "id":
                msg[f"_{k}"] = v if isinstance(v, (int, float, str)) else str(v)
        return msg

    async def forward(self, events):
        url = f"{self.config['url'].rstrip('/')}/gelf"
        sem = asyncio.Semaphore(int(self.config.get("concurrency") or 8))
        self.last_error = ""
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.config.get("verify_ssl", True)) as client:
            async def one(e):
                async with sem:
                    try:
                        resp = await client.post(url, json=self._gelf(clean_event(e)))
                        if resp.status_code in (200, 202):
                            return True
                        self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    except Exception as ex:
                        self.last_error = f"{type(ex).__name__}: {ex}"
                    return False
            results = await asyncio.gather(*(one(e) for e in events))
        ok = sum(results)
        return ok, len(events) - ok


@register_forwarder
class CoralogixForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="coralogix", display_name="Coralogix",
        description="Send OCSF events to Coralogix via the logs ingestion API",
        icon="coralogix", category="observability", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "api_key": {"type": "string", "title": "Send-Your-Data API Key", "secret": True},
                "domain": {"type": "string", "title": "Coralogix domain", "default": "coralogix.com",
                           "enum": ["coralogix.com", "eu2.coralogix.com", "coralogix.us", "cx498.coralogix.com", "coralogix.in", "coralogixsg.com"]},
                "ingest_url": {"type": "string", "title": "Ingest URL override (optional)"},
                "application_name": {"type": "string", "title": "Application name", "default": "gana"},
                "subsystem_name": {"type": "string", "title": "Subsystem name", "default": "ocsf"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["api_key"],
        },
    )

    # OCSF severity_id → Coralogix severity (1 debug … 6 critical)
    _sev = {0: 3, 1: 3, 2: 3, 3: 4, 4: 5, 5: 6, 6: 6}

    async def _request(self, batch):
        url = self.config.get("ingest_url") or f"https://ingress.{self.config.get('domain') or 'coralogix.com'}/logs/v1/singles"
        return {
            "method": "POST", "url": url,
            "headers": {"Authorization": f"Bearer {self.config['api_key']}", "Content-Type": "application/json"},
            "json": [{
                "applicationName": self.config.get("application_name") or "gana",
                "subsystemName": self.config.get("subsystem_name") or "ocsf",
                "computerName": "gana", "timestamp": event_time_ms(e),
                "severity": self._sev.get(e.get("severity_id"), 3), "text": e,
            } for e in batch],
        }


@register_forwarder
class MezmoForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="mezmo", display_name="Mezmo (LogDNA)",
        description="Send OCSF events to Mezmo via the log ingestion API",
        icon="mezmo", category="observability", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "ingestion_key": {"type": "string", "title": "Ingestion Key", "secret": True},
                "url": {"type": "string", "title": "Ingest URL", "default": "https://logs.mezmo.com/logs/ingest"},
                "hostname": {"type": "string", "title": "hostname", "default": "gana"},
                "app": {"type": "string", "title": "app", "default": "gana"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["ingestion_key"],
        },
    )

    async def _request(self, batch):
        return {
            "method": "POST",
            "url": self.config.get("url") or "https://logs.mezmo.com/logs/ingest",
            "params": {"hostname": self.config.get("hostname") or "gana", "now": int(time.time() * 1000)},
            "auth": (self.config["ingestion_key"], ""),
            "json": {"lines": [{
                "timestamp": event_time_ms(e), "line": json.dumps(e, default=str),
                "app": self.config.get("app") or "gana",
                "level": _SEVERITY_WORD.get(e.get("severity_id"), "info").upper(),
                "meta": {"class_uid": e.get("class_uid"), "class_name": e.get("class_name")},
            } for e in batch]},
        }


@register_forwarder
class BetterStackForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="betterstack", display_name="Better Stack (Logtail)",
        description="Send OCSF events to Better Stack Telemetry via a source's HTTP ingesting host",
        icon="betterstack", category="observability", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "source_token": {"type": "string", "title": "Source Token", "secret": True},
                "ingesting_host": {"type": "string", "title": "Ingesting host URL", "default": "https://in.logs.betterstack.com"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["source_token"],
        },
    )

    async def _request(self, batch):
        return {
            "method": "POST",
            "url": self.config.get("ingesting_host") or "https://in.logs.betterstack.com",
            "headers": {"Authorization": f"Bearer {self.config['source_token']}", "Content-Type": "application/json"},
            "json": [{"dt": event_time_iso(e), "message": event_summary(e), "ocsf": e} for e in batch],
        }


@register_forwarder
class SematextForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="sematext", display_name="Sematext Logs",
        description="Send OCSF events to a Sematext Logs App via its Elasticsearch-compatible Bulk API",
        icon="sematext", category="observability", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "app_token": {"type": "string", "title": "Logs App Token", "secret": True},
                "region": {"type": "string", "title": "Region", "default": "US", "enum": ["US", "EU"]},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["app_token"],
        },
    )

    def _ok(self, resp):
        # The Bulk API answers 200 even when individual documents fail
        return resp.status_code == 200 and not resp.json().get("errors", False)

    async def _request(self, batch):
        host = "logsene-receiver.eu.sematext.com" if self.config.get("region") == "EU" else "logsene-receiver.sematext.com"
        lines = []
        for e in batch:
            lines.append(json.dumps({"index": {"_index": self.config["app_token"]}}))
            lines.append(json.dumps({"@timestamp": event_time_iso(e), "message": event_summary(e), **e}, default=str))
        return {"method": "POST", "url": f"https://{host}/_bulk",
                "headers": {"Content-Type": "application/x-ndjson"}, "content": "\n".join(lines) + "\n"}


@register_forwarder
class LogicMonitorForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="logicmonitor", display_name="LogicMonitor (LM Logs)",
        description="Send OCSF events to LM Logs via the log ingestion API",
        icon="logicmonitor", category="observability", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "account": {"type": "string", "title": "Account (portal) name", "placeholder": "acme"},
                "bearer_token": {"type": "string", "title": "API Bearer Token", "secret": True},
                "resource_property": {"type": "string", "title": "Resource mapping property", "default": "system.hostname"},
                "resource_value": {"type": "string", "title": "Resource mapping value", "default": "gana"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["account", "bearer_token"],
        },
    )

    async def _request(self, batch):
        prop = self.config.get("resource_property") or "system.hostname"
        value = self.config.get("resource_value") or "gana"
        return {
            "method": "POST",
            "url": f"https://{self.config['account']}.logicmonitor.com/rest/log/ingest",
            "headers": {"Authorization": f"Bearer {self.config['bearer_token']}", "Content-Type": "application/json"},
            "json": [{"message": json.dumps(e, default=str), "timestamp": event_time_ms(e), "_lm.resourceId": {prop: value}}
                     for e in batch],
        }
