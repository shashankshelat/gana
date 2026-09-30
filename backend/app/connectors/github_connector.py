import hashlib
import hmac
import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class GitHubConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="github",
        display_name="GitHub",
        description="Ingest organization audit logs and security events from GitHub",
        icon="github",
        category="saas",
        auth_methods=["api_key", "oauth2"],
        supports_polling=True,
        supports_webhook=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "token": {"type": "string", "title": "Personal Access Token or App Token", "secret": True},
                "org": {"type": "string", "title": "Organization Name"},
                "webhook_secret": {"type": "string", "title": "Webhook Secret", "secret": True},
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string"},
                    "default": ["push", "pull_request", "repository", "member", "team"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["token"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "_document_id",
            "time": "created_at",
            "activity_name": "action",
            "app_name": "$const:GitHub",
            # Actor
            "actor.user.uid": "actor_id",
            "actor.user.name": "actor",
            # Source endpoint
            "src_endpoint.ip": "actor_ip",
            "src_endpoint.location.country": "actor_location.country_code",
            # Target resource
            "dst_endpoint.name": "repo",
            "cloud.account.uid": "org",
            # Affected user (when different from actor)
            "dst_endpoint.uid": "user",
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("token"):
            return False, "token is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {self.config['token']}", "Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                user = resp.json()
                return True, f"Connected as {user.get('login')}"
            return False, f"HTTP {resp.status_code}"

    def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
        secret = self.config.get("webhook_secret", "")
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        event_type = headers.get("x-github-event", "unknown")
        payload["_event_type"] = event_type
        return [payload]

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        org = self.config.get("org")
        if not org:
            return []
        events = []
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {
                "Authorization": f"token {self.config['token']}",
                "Accept": "application/vnd.github.v3+json",
            }
            params = {"per_page": 100}
            url = f"https://api.github.com/orgs/{org}/audit-log"
            while url:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code != 200:
                    break
                events.extend(resp.json())
                link = resp.headers.get("link", "")
                url = self._parse_next_link(link)
                params = {}
                if len(events) >= 10000:
                    break
        return events

    def _parse_next_link(self, link_header: str) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            parts = part.strip().split(";")
            if len(parts) == 2 and 'rel="next"' in parts[1]:
                return parts[0].strip().strip("<>")
        return None
