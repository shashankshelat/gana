import json
import hashlib
import hmac
import base64
import datetime
import httpx
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder


@register_forwarder
class AzureSentinelForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="azure_sentinel",
        display_name="Microsoft Sentinel",
        description="Forward OCSF events to Microsoft Sentinel via Log Analytics Data Collector API",
        icon="microsoft",
        category="siem",
        max_batch_size=5000,
        config_schema={
            "properties": {
                "workspace_id": {"type": "string", "title": "Log Analytics Workspace ID"},
                "shared_key": {"type": "string", "title": "Primary/Secondary Key", "secret": True},
                "log_type": {"type": "string", "title": "Custom Log Type Name", "default": "OCSF_Events"},
                "resource_id": {"type": "string", "title": "Azure Resource ID (optional)"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["workspace_id", "shared_key"],
        },
    )

    def _build_signature(self, date: str, content_length: int, method: str, content_type: str, resource: str) -> str:
        x_headers = f"x-ms-date:{date}"
        string_to_hash = f"{method}\n{content_length}\n{content_type}\n{x_headers}\n{resource}"
        bytes_to_hash = string_to_hash.encode("utf-8")
        decoded_key = base64.b64decode(self.config["shared_key"])
        encoded_hash = base64.b64encode(
            hmac.new(decoded_key, bytes_to_hash, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        return f"SharedKey {self.config['workspace_id']}:{encoded_hash}"

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["workspace_id", "shared_key"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            success, failed = await self.forward([{"_test": True, "class_uid": 3002, "time": 0}])
            if success:
                return True, "Test event sent successfully"
            return False, "Failed to send test event"
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        workspace_id = self.config["workspace_id"]
        log_type = self.config.get("log_type", "OCSF_Events")
        batch_size = self.config.get("batch_size", 500)
        url = f"https://{workspace_id}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01"

        success = 0
        failed = 0
        clean_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]

        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(clean_events), batch_size):
                batch = clean_events[i:i + batch_size]
                body = json.dumps(batch).encode("utf-8")
                now = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
                signature = self._build_signature(
                    date=now,
                    content_length=len(body),
                    method="POST",
                    content_type="application/json",
                    resource="/api/logs",
                )
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": signature,
                    "Log-Type": log_type,
                    "x-ms-date": now,
                    "time-generated-field": "time",
                }
                try:
                    resp = await client.post(url, content=body, headers=headers)
                    if resp.status_code == 200:
                        success += len(batch)
                    else:
                        failed += len(batch)
                except Exception:
                    failed += len(batch)

        return success, failed
