import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class AzureADConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="azure_ad",
        display_name="Azure Active Directory",
        description="Ingest sign-in and audit logs from Microsoft Azure AD via Microsoft Graph API",
        icon="microsoft",
        category="identity",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "tenant_id": {"type": "string", "title": "Tenant ID"},
                "client_id": {"type": "string", "title": "Client ID"},
                "client_secret": {"type": "string", "title": "Client Secret", "secret": True},
                "log_types": {
                    "type": "array",
                    "title": "Log Types",
                    "items": {"type": "string", "enum": ["signIns", "auditLogs", "directoryAudits"]},
                    "default": ["signIns", "auditLogs"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["tenant_id", "client_id", "client_secret"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id",
            "time": "createdDateTime",
            "status_id": {"path": "status.errorCode", "transform": "int"},
            "status_detail": "status.failureReason",
            # Actor / user
            "actor.user.uid": "userId",
            "actor.user.name": "userDisplayName",
            "actor.user.email_addr": "userPrincipalName",
            # Source endpoint
            "src_endpoint.ip": "ipAddress",
            "src_endpoint.location.city": "location.city",
            "src_endpoint.location.country": "location.countryOrRegion",
            "src_endpoint.location.state": "location.state",
            # App / service
            "app_name": "appDisplayName",
            "app_uid": "appId",
            # Device
            "device.uid": "deviceDetail.deviceId",
            "device.hostname": "deviceDetail.displayName",
            "device.os.name": "deviceDetail.operatingSystem",
            "device.os.version": "deviceDetail.browser",
            # Auth details
            "auth_protocol": "authenticationProtocol",
            "session.uid": "correlationId",
            # Cloud
            "cloud.account.uid": "tenantId",
        },
    )

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{self.config['tenant_id']}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                    "scope": "https://graph.microsoft.com/.default",
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
            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://graph.microsoft.com/v1.0/auditLogs/signIns?$top=1",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code in (200, 403):
                    return True, "Connection successful"
                return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_access_token()
        log_types = self.config.get("log_types", ["signIns"])
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}"}
            for log_type in log_types:
                url = f"https://graph.microsoft.com/v1.0/auditLogs/{log_type}?$top=1000"
                if since:
                    url += f"&$filter=createdDateTime ge {since}"

                while url:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    page_events = data.get("value", [])
                    for e in page_events:
                        e["_log_type"] = log_type
                    events.extend(page_events)
                    url = data.get("@odata.nextLink")
                    if len(events) >= 10000:
                        break

        return events
