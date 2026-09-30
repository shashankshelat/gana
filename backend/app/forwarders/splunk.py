import json
import logging
import httpx
from app.forwarders.base import BaseForwarder, ForwarderMeta, review_fields
from app.forwarders.registry import register_forwarder

logger = logging.getLogger(__name__)


@register_forwarder
class SplunkForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="splunk",
        display_name="Splunk HEC",
        description="Forward OCSF events to Splunk via HTTP Event Collector (HEC)",
        icon="splunk",
        category="siem",
        max_batch_size=500,
        config_schema={
            "properties": {
                "hec_url": {"type": "string", "title": "HEC URL", "placeholder": "https://splunk.example.com:8088"},
                "hec_token": {"type": "string", "title": "HEC Token", "secret": True},
                "index": {"type": "string", "title": "Splunk Index", "default": "ocsf"},
                "source": {"type": "string", "title": "Source", "default": "gana"},
                "sourcetype": {"type": "string", "title": "Sourcetype", "default": "_json"},
                "verify_ssl": {"type": "boolean", "title": "Verify SSL", "default": True},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 100},
                **review_fields("review_index", "Review index for unclassified events (blank = same index)", "ocsf_review"),
            },
            "required": ["hec_url", "hec_token"],
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["hec_url", "hec_token"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        # The health endpoint ignores the token, so send one real event to validate token + index
        url = f"{self.config['hec_url'].rstrip('/')}/services/collector/event"
        verify = self.config.get("verify_ssl", True)
        payload = self._hec_event({"class_uid": 0, "message": "GANA connection test"})
        async with httpx.AsyncClient(timeout=10, verify=verify) as client:
            try:
                resp = await client.post(url, content=json.dumps(payload), headers=self._headers())
                if resp.status_code == 200:
                    return True, f"Test event accepted by HEC (index={payload['index']})"
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Splunk {self.config['hec_token']}",
            "Content-Type": "application/json",
        }

    def _hec_event(self, event: dict) -> dict:
        index = self.config.get("index") or "ocsf"
        if self.config.get("review_index") and self.is_review(event):
            index = self.config["review_index"]
        hec_event = {
            "index": index,
            "source": self.config.get("source") or "gana",
            "sourcetype": self.config.get("sourcetype") or "_json",
            "event": event,
        }
        # OCSF time is epoch ms; omit when missing so Splunk uses receipt time instead of 1970
        ts = event.get("time")
        if isinstance(ts, (int, float)) and ts > 0:
            hec_event["time"] = ts / 1000.0
        return hec_event

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        url = f"{self.config['hec_url'].rstrip('/')}/services/collector/event"
        verify = self.config.get("verify_ssl", True)
        batch_size = int(self.config.get("batch_size") or 100)

        success = 0
        failed = 0

        async with httpx.AsyncClient(timeout=30, verify=verify) as client:
            # One request per index: if the review index is missing or not allowed for the token,
            # only those events fail, not the main-index ones sharing the batch
            by_index: dict[str, list[dict]] = {}
            for e in events:
                hec = self._hec_event(e)
                by_index.setdefault(hec["index"], []).append(hec)
            batches = [group[i:i + batch_size] for group in by_index.values() for i in range(0, len(group), batch_size)]
            for batch in batches:
                payload = "".join(json.dumps(h) for h in batch)
                try:
                    resp = await client.post(url, content=payload, headers=self._headers())
                    if resp.status_code == 200:
                        success += len(batch)
                    else:
                        failed += len(batch)
                        logger.error("Splunk HEC forwarder %s: HTTP %s %s",
                                     self.forwarder_id, resp.status_code, resp.text[:300])
                except Exception as e:
                    failed += len(batch)
                    logger.error("Splunk HEC forwarder %s: %s: %s", self.forwarder_id, type(e).__name__, e)

        return success, failed
