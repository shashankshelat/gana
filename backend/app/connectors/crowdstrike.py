import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class CrowdStrikeConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="crowdstrike",
        display_name="CrowdStrike Falcon",
        description="Ingest detection, incident, and audit events from CrowdStrike Falcon SIEM Connector",
        icon="shield",
        category="endpoint",
        auth_methods=["oauth2"],
        supports_polling=True,
        supports_streaming=True,
        default_ocsf_class_uid=2004,
        config_schema={
            "properties": {
                "client_id": {"type": "string", "title": "OAuth2 Client ID"},
                "client_secret": {"type": "string", "title": "OAuth2 Client Secret", "secret": True},
                "base_url": {
                    "type": "string",
                    "title": "Base URL",
                    "enum": ["https://api.crowdstrike.com", "https://api.eu-1.crowdstrike.com", "https://api.laggar.gcw.crowdstrike.com"],
                    "default": "https://api.crowdstrike.com",
                },
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string", "enum": ["detections", "incidents", "audit"]},
                    "default": ["detections", "incidents"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 60},
            },
            "required": ["client_id", "client_secret"],
        },
        default_mapping={
            # Detections REST API format (GET /detections/entities/summaries/v1)
            # Core event identity
            "metadata.uid": "detection_id",
            "time": "created_timestamp",
            "severity_id": "max_severity",
            "status_id": {"path": "status", "transform": "lower"},
            "activity_name": "behaviors[0].scenario",
            "finding.title": "behaviors[0].display_name",
            "finding.desc": "behaviors[0].description",
            "finding.uid": "detection_id",
            # Device / endpoint
            "device.uid": "device.device_id",
            "device.hostname": "device.hostname",
            "device.ip": "device.local_ip",
            "device.name": "device.hostname",
            "device.os.name": "device.platform_name",
            "device.os.version": "device.os_version",
            "device.domain": "device.machine_domain",
            # Actor
            "actor.user.name": "behaviors[0].user_name",
            "actor.process.name": "behaviors[0].filename",
            "actor.process.cmd_line": "behaviors[0].cmdline",
            "actor.process.file.path": "behaviors[0].filepath",
            "actor.process.file.hashes[0].value": "behaviors[0].sha256",
            "actor.process.file.hashes[0].algorithm_id": "$const:3",
            "actor.process.file.hashes[1].value": "behaviors[0].md5",
            "actor.process.file.hashes[1].algorithm_id": "$const:1",
            # MITRE ATT&CK
            "attacks[0].tactic.name": "behaviors[0].tactic",
            "attacks[0].technique.name": "behaviors[0].technique",
            "attacks[0].technique.uid": "behaviors[0].technique_id",
            # Streaming API format (event envelope) — override time if streaming
            # "time": "metadata.eventCreationTime",   # streaming: epoch ms
            # "actor.user.name": "event.UserName",    # streaming
            # "src_endpoint.ip": "event.LocalIP",     # streaming
        },
    )

    async def _get_token(self) -> str:
        base_url = self.config.get("base_url", "https://api.crowdstrike.com")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/oauth2/token",
                data={
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["client_id", "client_secret"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            token = await self._get_token()
            return True, "OAuth2 token acquired successfully"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_token()
        base_url = self.config.get("base_url", "https://api.crowdstrike.com")
        event_types = self.config.get("event_types", ["detections"])
        headers = {"Authorization": f"Bearer {token}"}
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            for event_type in event_types:
                if event_type == "detections":
                    resp = await client.get(
                        f"{base_url}/detects/queries/detects/v1",
                        headers=headers,
                        params={"limit": 1000, "sort": "created_timestamp.desc"},
                    )
                    if resp.status_code == 200:
                        ids = resp.json().get("resources", [])
                        if ids:
                            det_resp = await client.post(
                                f"{base_url}/detects/entities/summaries/GET/v1",
                                headers=headers,
                                json={"ids": ids[:1000]},
                            )
                            if det_resp.status_code == 200:
                                dets = det_resp.json().get("resources", [])
                                for d in dets:
                                    d["_event_type"] = "detection"
                                events.extend(dets)

                elif event_type == "incidents":
                    resp = await client.get(
                        f"{base_url}/incidents/queries/incidents/v1",
                        headers=headers,
                        params={"limit": 500},
                    )
                    if resp.status_code == 200:
                        ids = resp.json().get("resources", [])
                        if ids:
                            inc_resp = await client.post(
                                f"{base_url}/incidents/entities/incidents/GET/v1",
                                headers=headers,
                                json={"ids": ids[:500]},
                            )
                            if inc_resp.status_code == 200:
                                incs = inc_resp.json().get("resources", [])
                                for i in incs:
                                    i["_event_type"] = "incident"
                                events.extend(incs)

        return events
