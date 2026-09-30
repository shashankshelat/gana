import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class Microsoft365Connector(BaseConnector):
    meta = ConnectorMeta(
        type_id="microsoft_365",
        display_name="Microsoft 365",
        description="Ingest audit and activity logs from Microsoft 365 via Office 365 Management API",
        icon="microsoft",
        category="saas",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "tenant_id": {"type": "string", "title": "Tenant ID"},
                "client_id": {"type": "string", "title": "Client ID"},
                "client_secret": {"type": "string", "title": "Client Secret", "secret": True},
                "content_types": {
                    "type": "array",
                    "title": "Content Types",
                    "items": {"type": "string", "enum": [
                        "Audit.AzureActiveDirectory",
                        "Audit.Exchange",
                        "Audit.SharePoint",
                        "Audit.General",
                        "DLP.All"
                    ]},
                    "default": ["Audit.AzureActiveDirectory", "Audit.General"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["tenant_id", "client_id", "client_secret"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "Id",
            "time": "CreationTime",
            "activity_name": "Operation",
            "status_id": {"path": "ResultStatus", "transform": "lower"},
            # Actor
            "actor.user.uid": "UserId",
            "actor.user.name": "UserKey",
            "actor.user.type": "UserType",
            # Source endpoint
            "src_endpoint.ip": "ClientIP",
            "http_request.user_agent": "UserAgent",
            # Target resource
            "dst_endpoint.name": "ObjectId",
            # Application / workload
            "app_name": "Workload",
            # Cloud / tenant
            "cloud.account.uid": "OrganizationId",
            # Device (when present)
            "device.hostname": "DeviceName",
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
                    "scope": "https://manage.office.com/.default",
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
            token = await self._get_token()
            return True, "OAuth2 token acquired"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_token()
        tenant_id = self.config["tenant_id"]
        content_types = self.config.get("content_types", ["Audit.General"])
        headers = {"Authorization": f"Bearer {token}"}
        events = []

        async with httpx.AsyncClient(timeout=60) as client:
            for content_type in content_types:
                sub_resp = await client.post(
                    f"https://manage.office.com/api/v1.0/{tenant_id}/activity/feed/subscriptions/start",
                    headers=headers,
                    json={"contentType": content_type},
                )

                list_resp = await client.get(
                    f"https://manage.office.com/api/v1.0/{tenant_id}/activity/feed/subscriptions/content",
                    headers=headers,
                    params={"contentType": content_type},
                )

                if list_resp.status_code == 200:
                    blobs = list_resp.json()
                    for blob in blobs[:20]:
                        content_url = blob.get("contentUri")
                        if content_url:
                            content_resp = await client.get(content_url, headers=headers)
                            if content_resp.status_code == 200:
                                for record in content_resp.json():
                                    record["_content_type"] = content_type
                                    events.append(record)
        return events
