import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class MicrosoftDefenderConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="microsoft_defender",
        display_name="Microsoft Defender for Endpoint",
        description="Ingest alerts and incidents from Microsoft Defender for Endpoint via Graph Security API",
        icon="microsoft",
        category="endpoint",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=2004,
        config_schema={
            "properties": {
                "tenant_id": {"type": "string", "title": "Tenant ID"},
                "client_id": {"type": "string", "title": "Client ID"},
                "client_secret": {"type": "string", "title": "Client Secret", "secret": True},
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string", "enum": ["alerts", "incidents", "vulnerabilities"]},
                    "default": ["alerts", "incidents"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 60},
            },
            "required": ["tenant_id", "client_id", "client_secret"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id",
            "time": "createdDateTime",
            "activity_name": "category",
            "severity_id": {"path": "severity", "transform": "lower"},
            "status_id": {"path": "status", "transform": "lower"},
            # Finding
            "finding.title": "title",
            "finding.desc": "description",
            "finding.uid": "id",
            "finding.remediation.desc": "recommendedActions",
            # Device / endpoint
            "device.uid": "machineId",
            "device.hostname": "computerDnsName",
            "device.ip": "networkInterfaces[0].publicIPv4Address",
            "device.os.name": "osPlatform",
            "device.os.version": "osVersion",
            # Actor / user
            "actor.user.name": "relatedUser.userName",
            "actor.user.domain": "relatedUser.domainName",
            # Process (initiating)
            "actor.process.name": "evidence[0].fileName",
            "actor.process.file.path": "evidence[0].filePath",
            "actor.process.file.hashes[0].value": "evidence[0].sha256",
            "actor.process.file.hashes[0].algorithm_id": "$const:3",
            # MITRE
            "attacks[0].tactic.name": "mitreTechniques[0]",
            # Network
            "src_endpoint.ip": "evidence[0].ipAddress",
        },
    )

    async def _get_token(self) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{self.config['tenant_id']}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                    "scope": "https://api.securitycenter.microsoft.com/.default",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["tenant_id", "client_id", "client_secret"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await self._get_token()
            return True, "OAuth2 token acquired"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_token()
        event_types = self.config.get("event_types", ["alerts"])
        headers = {"Authorization": f"Bearer {token}"}
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            for event_type in event_types:
                url = f"https://api.securitycenter.microsoft.com/api/{event_type}?$top=1000"
                if since:
                    url += f"&$filter=createdDateTime ge {since}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    type_events = data.get("value", [])
                    for e in type_events:
                        e["_event_type"] = event_type
                    events.extend(type_events)

        return events
