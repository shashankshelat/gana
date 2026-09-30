from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class GenericWebhookConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="generic_webhook",
        display_name="Generic Webhook",
        description="Receive events from any source via HTTP POST webhook. Configure field mappings manually.",
        icon="webhook",
        category="custom",
        auth_methods=["webhook"],
        supports_webhook=True,
        default_ocsf_class_uid=0,  # unknown logs: Base Event until routes classify them
        config_schema={
            "properties": {
                "secret": {"type": "string", "title": "Webhook Secret (HMAC)", "secret": True},
                "signature_header": {"type": "string", "title": "Signature Header Name", "default": "X-Webhook-Signature"},
                "signature_algorithm": {
                    "type": "string",
                    "title": "Signature Algorithm",
                    "enum": ["hmac_sha256", "hmac_sha1", "none"],
                    "default": "hmac_sha256",
                },
                "events_path": {"type": "string", "title": "JSON Path to Events Array", "placeholder": "data.events"},
                "content_type": {
                    "type": "string",
                    "title": "Expected Content Type",
                    "enum": ["application/json", "application/x-www-form-urlencoded", "text/plain"],
                    "default": "application/json",
                },
            },
        },
        default_mapping={},
    )

    async def validate_config(self) -> tuple[bool, str]:
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        return True, "Webhook endpoint is ready"

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        events_path = self.config.get("events_path")
        if events_path:
            events = self.get_nested(payload, events_path)
            if isinstance(events, list):
                return events
        if isinstance(payload, list):
            return payload
        return [payload]
