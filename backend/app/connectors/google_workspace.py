import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class GoogleWorkspaceConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="google_workspace",
        display_name="Google Workspace",
        description="Ingest admin, login, and Drive activity logs from Google Workspace Reports API",
        icon="google",
        category="saas",
        auth_methods=["oauth2"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "service_account_json": {"type": "string", "title": "Service Account JSON", "secret": True, "multiline": True},
                "admin_email": {"type": "string", "title": "Admin Email (for delegation)"},
                "applications": {
                    "type": "array",
                    "title": "Applications",
                    "items": {"type": "string", "enum": ["admin", "login", "drive", "token", "groups", "meet"]},
                    "default": ["admin", "login"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["service_account_json", "admin_email"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id.uniqueQualifier",
            "time": "id.time",
            "activity_name": "events[0].name",
            "app_name": "id.applicationName",
            # Actor
            "actor.user.email_addr": "actor.email",
            "actor.user.uid": "actor.profileId",
            "actor.user.full_name": "actor.displayName",
            # Source endpoint
            "src_endpoint.ip": "ipAddress",
            # Cloud / account
            "cloud.account.uid": "id.customerId",
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("service_account_json"):
            return False, "service_account_json is required"
        if not self.config.get("admin_email"):
            return False, "admin_email is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.googleapis.com/admin/reports/v1/activity/users/all/applications/login?maxResults=1",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code in (200, 403):
                    return True, "Connection successful"
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, str(e)

    async def _get_access_token(self) -> str:
        import json
        import time
        import jwt as pyjwt

        sa_info = json.loads(self.config["service_account_json"])
        now = int(time.time())
        claim = {
            "iss": sa_info["client_email"],
            "sub": self.config["admin_email"],
            "scope": "https://www.googleapis.com/auth/admin.reports.audit.readonly",
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

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = await self._get_access_token()
        applications = self.config.get("applications", ["login"])
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}"}
            for app in applications:
                url = f"https://www.googleapis.com/admin/reports/v1/activity/users/all/applications/{app}?maxResults=1000"
                if since:
                    url += f"&startTime={since}"
                while url:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    page_events = data.get("items", [])
                    for e in page_events:
                        e["_application"] = app
                    events.extend(page_events)
                    url = data.get("nextPageToken")
                    if url:
                        url = f"https://www.googleapis.com/admin/reports/v1/activity/users/all/applications/{app}?pageToken={url}&maxResults=1000"
                    if len(events) >= 10000:
                        break
        return events
