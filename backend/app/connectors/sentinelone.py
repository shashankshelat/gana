import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class SentinelOneConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="sentinelone",
        display_name="SentinelOne",
        description="Ingest threat detections, activities, and alerts from SentinelOne EDR",
        icon="shield",
        category="endpoint",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=2004,
        config_schema={
            "properties": {
                "management_url": {"type": "string", "title": "Management URL", "placeholder": "https://usea1.sentinelone.net"},
                "api_token": {"type": "string", "title": "API Token", "secret": True},
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string", "enum": ["threats", "activities", "alerts"]},
                    "default": ["threats", "activities"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 60},
            },
            "required": ["management_url", "api_token"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id",
            "time": "createdAt",
            "severity_id": {"path": "threatInfo.confidenceLevel", "transform": "lower"},
            "status_id": {"path": "threatInfo.mitigationStatus", "transform": "lower"},
            # Finding
            "finding.title": "threatInfo.threatName",
            "finding.desc": "threatInfo.classification",
            "finding.uid": "id",
            # Device
            "device.uid": "agentRealtimeInfo.agentId",
            "device.hostname": "agentRealtimeInfo.agentComputerName",
            "device.ip": "agentRealtimeInfo.agentIpV4",
            "device.os.name": "agentRealtimeInfo.agentOsName",
            "device.os.version": "agentRealtimeInfo.agentOsRevision",
            "device.domain": "agentRealtimeInfo.agentDomain",
            # Malware / file
            "malware.name": "threatInfo.threatName",
            "file.path": "threatInfo.filePath",
            "file.name": "threatInfo.fileName",
            "file.hashes[0].value": "threatInfo.sha256",
            "file.hashes[0].algorithm_id": "$const:3",
            "file.hashes[1].value": "threatInfo.md5",
            "file.hashes[1].algorithm_id": "$const:1",
            # Actor / process
            "actor.process.cmd_line": "threatInfo.maliciousProcessArguments",
            "actor.user.name": "threatInfo.processUser",
            # MITRE
            "attacks[0].tactic.name": "mitigationReport.library.mispMalwareFamilies[0]",
        },
    )

    def _headers(self) -> dict:
        return {
            "Authorization": f"ApiToken {self.config['api_token']}",
            "Content-Type": "application/json",
        }

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["management_url", "api_token"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        base = self.config["management_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{base}/web/api/v2.1/system/status", headers=self._headers())
                if resp.status_code == 200:
                    return True, "Connected to SentinelOne"
                return False, f"HTTP {resp.status_code}"
            except Exception as e:
                return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        base = self.config["management_url"].rstrip("/")
        event_types = self.config.get("event_types", ["threats"])
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            headers = self._headers()
            for event_type in event_types:
                if event_type == "threats":
                    url = f"{base}/web/api/v2.1/threats"
                    params = {"limit": 1000, "sortBy": "createdAt", "sortOrder": "desc"}
                elif event_type == "activities":
                    url = f"{base}/web/api/v2.1/activities"
                    params = {"limit": 1000, "sortBy": "createdAt", "sortOrder": "desc"}
                elif event_type == "alerts":
                    url = f"{base}/web/api/v2.1/cloud-detection/alerts"
                    params = {"limit": 1000}
                else:
                    continue

                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    for item in items:
                        item["_event_type"] = event_type
                    events.extend(items)
        return events
