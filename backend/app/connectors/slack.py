import hashlib
import hmac
import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector



def _slack_common(activity_id: int, activity_name: str) -> dict:
    """Fields every Slack Events API event maps the same way."""
    return {
        "time": {"path": "event_ts", "transform": "epoch_ms"},
        "activity_id": f"$const:{activity_id}",
        "activity_name": f"$const:{activity_name}",
        "severity_id": "$const:1",
        "status_id": "$const:success",
        "metadata.event_code": "type",
        "metadata.product.name": "$const:Slack",
        "metadata.product.vendor_name": "$const:Slack",
    }


# OCSF classes and activity ids verified against schema.ocsf.io (Group Management 3006,
# Account Change 3001, File Hosting Activity 6006).
SLACK_EVENT_ROUTES = [
    {
        "name": "channel_created",
        "when": {"field": "type", "equals": "channel_created"},
        "class_uid": 3006,
        "mapping": {
            **_slack_common(6, "Create"),
            "group.uid": "channel.id",
            "group.name": "channel.name",
            "group.type": "$const:Channel",
            "actor.user.uid": "channel.creator",
            "unmapped.is_private": "channel.is_private",
            "unmapped.is_shared": "channel.is_shared",
            "cloud.account.uid": "channel.context_team_id",
        },
    },
    {
        "name": "channel_deleted",
        "when": {"field": "type", "equals": "channel_deleted"},
        "class_uid": 3006,
        "mapping": {
            **_slack_common(5, "Delete"),
            "group.uid": "channel",
            "group.type": "$const:Channel",
            "actor.user.uid": "actor_id",
        },
    },
    {
        "name": "member_joined_channel",
        "when": {"field": "type", "equals": "member_joined_channel"},
        "class_uid": 3006,
        "mapping": {
            **_slack_common(3, "Add User"),
            "user.uid": "user",
            "group.uid": "channel",
            "group.type": "channel_type",
            "actor.user.uid": "inviter",
            "cloud.account.uid": "team",
        },
    },
    {
        "name": "member_left_channel",
        "when": {"field": "type", "equals": "member_left_channel"},
        "class_uid": 3006,
        "mapping": {
            **_slack_common(4, "Remove User"),
            "user.uid": "user",
            "group.uid": "channel",
            "group.type": "channel_type",
            "cloud.account.uid": "team",
        },
    },
    {
        "name": "team_join",
        "when": {"field": "type", "equals": "team_join"},
        "class_uid": 3001,
        "mapping": {
            **_slack_common(1, "Create"),
            "user.uid": "user.id",
            "user.name": "user.name",
            "user.full_name": "user.real_name",
            "user.email_addr": "user.profile.email",
            "cloud.account.uid": "user.team_id",
            "unmapped.is_admin": "user.is_admin",
            "unmapped.is_bot": "user.is_bot",
        },
    },
    {
        "name": "user_change",
        "when": {"field": "type", "equals": "user_change"},
        "class_uid": 3001,
        "mapping": {
            **_slack_common(99, "Other"),
            "user.uid": "user.id",
            "user.name": "user.name",
            "user.full_name": "user.real_name",
            "user.email_addr": "user.profile.email",
            "cloud.account.uid": "user.team_id",
            "unmapped.deleted": "user.deleted",
            "unmapped.is_admin": "user.is_admin",
            "unmapped.is_restricted": "user.is_restricted",
        },
    },
    {
        "name": "file_shared",
        "when": {"field": "type", "equals": "file_shared"},
        "class_uid": 6006,
        "mapping": {
            **_slack_common(12, "Share"),
            "file.uid": "file_id",
            "actor.user.uid": "user_id",
            "unmapped.channel_id": "channel_id",
        },
    },
]


@register_connector
class SlackConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="slack",
        display_name="Slack",
        description="Ingest audit logs from Slack via Audit API or Events API webhook",
        icon="slack",
        category="saas",
        auth_methods=["api_key", "oauth2"],
        supports_polling=True,
        supports_webhook=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "bot_token": {"type": "string", "title": "Bot Token (xoxb-...)", "secret": True},
                "signing_secret": {"type": "string", "title": "Signing Secret", "secret": True},
                "audit_api_token": {"type": "string", "title": "Audit API Token (Enterprise)", "secret": True},
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["signing_secret"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "id",
            "time": "date_create",
            "activity_name": "action",
            "app_name": "$const:Slack",
            # Actor
            "actor.user.uid": "actor.user.id",
            "actor.user.name": "actor.user.name",
            "actor.user.email_addr": "actor.user.email",
            "actor.user.type": "actor.type",
            # Source endpoint
            "src_endpoint.ip": "context.ip_address",
            # Entity acted upon
            "dst_endpoint.uid": "entity.user.id",
            "dst_endpoint.name": "entity.channel.id",
            # Workspace
            "cloud.account.uid": "context.team_id",
            # Events API events differ per type and belong to different OCSF classes; the flat rules
            # above remain the fallback for Audit Logs API (Enterprise Grid) entries.
            "_routes": SLACK_EVENT_ROUTES,
            "_default_class_uid": 0,
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("signing_secret") and not self.config.get("audit_api_token"):
            return False, "signing_secret or audit_api_token is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        token = self.config.get("bot_token") or self.config.get("audit_api_token")
        if not token:
            return False, "No API token configured"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("ok"):
                return True, f"Connected as {data.get('user', 'unknown')}"
            return False, data.get("error", "Unknown error")

    def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
        signing_secret = self.config.get("signing_secret", "")
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")
        if not signing_secret or not timestamp or not signature:
            return False
        # Slack's replay protection: reject requests older than 5 minutes
        import time
        try:
            if abs(time.time() - int(timestamp)) > 300:
                return False
        except ValueError:
            return False
        base_string = f"v0:{timestamp}:{payload.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            signing_secret.encode(), base_string.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        if payload.get("type") == "url_verification":
            return []
        event = payload.get("event", payload)
        return [event]

    def polling_configured(self) -> tuple[bool, str]:
        if self.config.get("audit_api_token"):
            return True, ""
        return False, "No Audit API token (Enterprise Grid only); events arrive via the Events API webhook instead"

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        token = self.config.get("audit_api_token")
        if not token:
            return []
        events = []
        async with httpx.AsyncClient(timeout=30) as client:
            params = {"limit": 9999}
            if since:
                # Audit Logs API takes epoch seconds; the poller passes ISO 8601
                from datetime import datetime
                params["oldest"] = since if since.isdigit() else int(
                    datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
                )
            resp = await client.get(
                "https://api.slack.com/audit/v1/logs",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code != 200 or data.get("ok") is False:
                # Surface Slack's reason (e.g. not_allowed_token_type, missing_scope) instead of "0 events"
                raise RuntimeError(f"Slack Audit Logs API: HTTP {resp.status_code} {data.get('error', resp.text[:200])}")
            events = data.get("entries", [])
        return events
