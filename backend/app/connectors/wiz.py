import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class WizConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="wiz",
        display_name="Wiz",
        description="Ingest cloud security issues, misconfigurations, and vulnerabilities from Wiz",
        icon="shield",
        category="cloud_security",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=2002,
        config_schema={
            "properties": {
                "client_id": {"type": "string", "title": "Service Account Client ID"},
                "client_secret": {"type": "string", "title": "Service Account Client Secret", "secret": True},
                "auth_url": {"type": "string", "title": "Auth URL", "default": "https://auth.app.wiz.io/oauth/token"},
                "api_endpoint": {"type": "string", "title": "API Endpoint", "default": "https://api.us20.app.wiz.io/graphql"},
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string", "enum": ["issues", "vulnerabilities", "audit_logs"]},
                    "default": ["issues"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["client_id", "client_secret"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id",
            "time": "createdAt",
            "severity_id": {"path": "severity", "transform": "lower"},
            "status_id": {"path": "status", "transform": "lower"},
            # Finding
            "finding.title": "control.name",
            "finding.uid": "control.id",
            "finding.desc": "description",
            "finding.type": "type.name",
            # Cloud resource
            "cloud.account.uid": "projects[0].id",
            "cloud.account.name": "projects[0].name",
            "cloud.provider": "projects[0].cloudPlatform",
            "cloud.region": "entitySnapshot.region",
            # Affected resource
            "dst_endpoint.name": "entitySnapshot.name",
            "dst_endpoint.uid": "entitySnapshot.id",
            "dst_endpoint.type": "entitySnapshot.type",
        },
    )

    async def _get_token(self) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.config.get("auth_url", "https://auth.app.wiz.io/oauth/token"),
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                    "audience": "wiz-api",
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
        endpoint = self.config.get("api_endpoint", "https://api.us20.app.wiz.io/graphql")
        events = []

        query = """
        query IssuesList($first: Int) {
          issues(first: $first, filterBy: {status: [OPEN, IN_PROGRESS]}) {
            nodes {
              id createdAt updatedAt status severity
              description
              control { name }
              entitySnapshot { name type }
              projects { id cloudPlatform }
            }
          }
        }"""

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                endpoint,
                json={"query": query, "variables": {"first": 500}},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
                for n in nodes:
                    n["_event_type"] = "issue"
                events.extend(nodes)

        return events
