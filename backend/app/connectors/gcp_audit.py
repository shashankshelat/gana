import json
import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class GCPAuditConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="gcp_audit",
        display_name="GCP Cloud Audit Logs",
        description="Ingest Admin Activity and Data Access audit logs from Google Cloud Platform",
        icon="google",
        category="cloud",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=3005,
        config_schema={
            "properties": {
                "service_account_json": {"type": "string", "title": "Service Account JSON", "secret": True, "multiline": True},
                "project_id": {"type": "string", "title": "GCP Project ID"},
                "log_filter": {
                    "type": "string",
                    "title": "Log Filter",
                    "default": 'logName:"cloudaudit.googleapis.com"',
                },
                "page_size": {"type": "integer", "title": "Page Size", "default": 1000},
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["service_account_json", "project_id"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "insertId",
            "time": "timestamp",
            "severity_id": {"path": "severity", "transform": "lower"},
            "status_id": {"path": "protoPayload.status.code", "transform": "int"},
            "status_detail": "protoPayload.status.message",
            # API operation
            "api.operation": "protoPayload.methodName",
            "api.service.name": "protoPayload.serviceName",
            "api.version": "protoPayload.resourceName",
            # Actor
            "actor.user.email_addr": "protoPayload.authenticationInfo.principalEmail",
            "actor.user.uid": "protoPayload.authenticationInfo.principalEmail",
            "actor.user.type": "protoPayload.authenticationInfo.principalSubject",
            # Source endpoint
            "src_endpoint.ip": "protoPayload.requestMetadata.callerIp",
            "http_request.user_agent": "protoPayload.requestMetadata.callerSuppliedUserAgent",
            # Cloud / resource
            "cloud.account.uid": "resource.labels.project_id",
            "cloud.region": "resource.labels.location",
            "cloud.resource.uid": "protoPayload.resourceName",
            "cloud.resource.type": "resource.type",
            # Log metadata
            "activity_name": "logName",
        },
    )

    async def _get_token(self) -> str:
        import time
        try:
            import jwt as pyjwt
        except ImportError:
            raise ImportError("PyJWT is required for GCP auth")

        sa_info = json.loads(self.config["service_account_json"])
        now = int(time.time())
        claim = {
            "iss": sa_info["client_email"],
            "scope": "https://www.googleapis.com/auth/logging.read",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(claim, sa_info["private_key"], algorithm="RS256")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": token},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("service_account_json"):
            return False, "service_account_json is required"
        if not self.config.get("project_id"):
            return False, "project_id is required"
        try:
            json.loads(self.config["service_account_json"])
        except json.JSONDecodeError:
            return False, "service_account_json is not valid JSON"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await self._get_token()
            return True, "GCP token acquired"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_token()
        project_id = self.config["project_id"]
        log_filter = self.config.get("log_filter", 'logName:"cloudaudit.googleapis.com"')
        page_size = self.config.get("page_size", 1000)
        entries = []

        async with httpx.AsyncClient(timeout=60) as client:
            headers = {"Authorization": f"Bearer {token}"}
            body = {
                "resourceNames": [f"projects/{project_id}"],
                "filter": log_filter,
                "orderBy": "timestamp desc",
                "pageSize": page_size,
            }
            resp = await client.post(
                "https://logging.googleapis.com/v2/entries:list",
                headers=headers,
                json=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("entries", [])
        return entries
