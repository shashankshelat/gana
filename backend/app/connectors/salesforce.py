import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class SalesforceConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="salesforce",
        display_name="Salesforce",
        description="Ingest login history and event monitoring logs from Salesforce",
        icon="cloud",
        category="saas",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "instance_url": {"type": "string", "title": "Instance URL", "placeholder": "https://myorg.salesforce.com"},
                "client_id": {"type": "string", "title": "Connected App Client ID"},
                "client_secret": {"type": "string", "title": "Connected App Client Secret", "secret": True},
                "username": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password + Security Token", "secret": True},
                "api_version": {"type": "string", "title": "API Version", "default": "v59.0"},
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["instance_url", "client_id", "client_secret", "username", "password"],
        },
        default_mapping={
            # Core event identity (EventLogFile uses UPPERCASE field names)
            "metadata.uid": "REQUEST_ID",
            "time": "TIMESTAMP_DERIVED",
            "activity_name": "EVENT_TYPE",
            "status_id": {"path": "LOGIN_STATUS", "transform": "lower"},
            "app_name": "$const:Salesforce",
            # Actor / user
            "actor.user.uid": "USER_ID",
            "actor.user.name": "USERNAME",
            "actor.user.email_addr": "USER_EMAIL",
            # Source endpoint
            "src_endpoint.ip": "SOURCE_IP",
            "src_endpoint.location.city": "CITY",
            "src_endpoint.location.country": "COUNTRY_ISO",
            # Client
            "http_request.user_agent": "BROWSER_TYPE",
            "src_endpoint.os": "PLATFORM_TYPE",
            # Session
            "session.uid": "SESSION_KEY",
            # Cloud / org
            "cloud.account.uid": "ORGANIZATION_ID",
        },
    )

    async def _get_token(self) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.config['instance_url']}/services/oauth2/token",
                data={
                    "grant_type": "password",
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                    "username": self.config["username"],
                    "password": self.config["password"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["access_token"], data["instance_url"]

    async def validate_config(self) -> tuple[bool, str]:
        required = ["instance_url", "client_id", "client_secret", "username", "password"]
        for field in required:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            token, instance = await self._get_token()
            return True, f"Connected to {instance}"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token, instance = await self._get_token()
        version = self.config.get("api_version", "v59.0")
        headers = {"Authorization": f"Bearer {token}"}
        events = []

        query = "SELECT Id,LOGIN_TIME,USER_ID,USER_NAME,SOURCE_IP,STATUS,BROWSER_TYPE FROM LoginHistory ORDER BY LOGIN_TIME DESC LIMIT 1000"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{instance}/services/data/{version}/query/",
                headers=headers,
                params={"q": query},
            )
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("records", [])
                for r in records:
                    r.pop("attributes", None)
                events.extend(records)

        return events
