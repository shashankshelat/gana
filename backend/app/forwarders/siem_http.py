"""SIEM destinations with HTTP ingestion: Devo, SentinelOne Singularity Data Lake, Panther, OpenSearch."""
import hashlib
import hmac
import json

from app.forwarders._common import BETA_NOTE, HttpBatchForwarder, event_time_ms
from app.forwarders.base import ForwarderMeta
from app.forwarders.elasticsearch import ElasticsearchForwarder
from app.forwarders.registry import register_forwarder


def _ndjson(batch: list[dict]) -> str:
    return "\n".join(json.dumps(e, default=str) for e in batch) + "\n"


@register_forwarder
class DevoForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="devo", display_name="Devo",
        description="Send OCSF events to Devo through the HTTP ingestion API (stream endpoint, one event per line)",
        icon="devo", category="siem", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "endpoint": {"type": "string", "title": "HTTP ingestion endpoint", "default": "https://http-us.devo.io"},
                "domain": {"type": "string", "title": "Domain"},
                "token": {"type": "string", "title": "HTTP token", "secret": True},
                "hostname": {"type": "string", "title": "hostname", "default": "gana"},
                "tag": {"type": "string", "title": "Tag (custom tags start with my.app.)", "default": "my.app.gana.ocsf"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["domain", "token"],
        },
    )

    async def _request(self, batch):
        c = self.config
        return {
            "method": "POST",
            "url": f"{(c.get('endpoint') or 'https://http-us.devo.io').rstrip('/')}/stream/{c['domain']}/token!{c['token']}"
                   f"/{c.get('hostname') or 'gana'}/{c.get('tag') or 'my.app.gana.ocsf'}",
            "headers": {"Content-Type": "text/plain"},
            "content": _ndjson(batch),
        }


@register_forwarder
class SentinelOneDataLakeForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="sentinelone_siem", display_name="SentinelOne Singularity Data Lake (AI SIEM)",
        description="Send OCSF events to Singularity Data Lake through its HEC-compatible ingestion endpoint",
        icon="sentinelone", category="siem", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "HEC ingest URL", "default": "https://ingest.us1.sentinelone.net/services/collector/event"},
                "api_key": {"type": "string", "title": "Log Write API Key", "secret": True},
                "auth_scheme": {"type": "string", "title": "Authorization scheme", "default": "Bearer", "enum": ["Bearer", "Splunk"]},
                "sourcetype": {"type": "string", "title": "sourcetype", "default": "ocsf"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["url", "api_key"],
        },
    )

    async def _request(self, batch):
        body = "".join(json.dumps({"time": event_time_ms(e) / 1000, "sourcetype": self.config.get("sourcetype") or "ocsf",
                                   "source": "gana", "event": e}, default=str) for e in batch)
        return {
            "method": "POST", "url": self.config["url"],
            "headers": {"Authorization": f"{self.config.get('auth_scheme') or 'Bearer'} {self.config['api_key']}",
                        "Content-Type": "application/json"},
            "content": body,
        }


@register_forwarder
class PantherForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="panther", display_name="Panther",
        description="Send OCSF events to a Panther HTTP log source (JSON lines)",
        icon="panther", category="siem", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "HTTP source ingest URL", "placeholder": "https://logs.<instance>.runpanther.net/http/<source-id>"},
                "auth_method": {"type": "string", "title": "Auth method", "default": "shared_secret", "enum": ["shared_secret", "bearer", "hmac", "none"]},
                "header_name": {"type": "string", "title": "Header name (shared secret / HMAC)", "default": "x-panther-secret"},
                "secret": {"type": "string", "title": "Secret / token", "secret": True},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["url"],
        },
    )

    async def _request(self, batch):
        body = _ndjson(batch)
        headers = {"Content-Type": "application/x-ndjson"}
        method, secret = self.config.get("auth_method") or "shared_secret", self.config.get("secret") or ""
        header = self.config.get("header_name") or "x-panther-secret"
        if method == "shared_secret":
            headers[header] = secret
        elif method == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif method == "hmac":
            headers[header] = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return {"method": "POST", "url": self.config["url"], "headers": headers, "content": body}


@register_forwarder
class OpenSearchForwarder(ElasticsearchForwarder):
    """OpenSearch accepts the same Bulk API, so this reuses the Elasticsearch forwarder."""
    meta = ForwarderMeta(
        type_id="opensearch", display_name="OpenSearch",
        description="Send OCSF events to OpenSearch (self-managed or Amazon OpenSearch Service) via the Bulk API",
        icon="opensearch", category="siem", max_batch_size=5000, maturity="beta",
        maturity_note="Shares the Elasticsearch forwarder's Bulk API code; not yet verified against a live OpenSearch cluster.",
        config_schema={
            **ElasticsearchForwarder.meta.config_schema,
            "properties": {
                **ElasticsearchForwarder.meta.config_schema["properties"],
                "url": {"type": "string", "title": "OpenSearch URL", "placeholder": "https://search-domain.us-east-1.es.amazonaws.com"},
            },
        },
    )
