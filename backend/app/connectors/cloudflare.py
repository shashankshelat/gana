import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class CloudflareConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="cloudflare",
        display_name="Cloudflare",
        description="Ingest HTTP, firewall, DNS, and audit events from Cloudflare Logpush or API",
        icon="cloud",
        category="network",
        auth_methods=["api_key"],
        supports_polling=True,
        supports_webhook=True,
        default_ocsf_class_uid=4001,
        config_schema={
            "properties": {
                "api_token": {"type": "string", "title": "API Token", "secret": True},
                "account_id": {"type": "string", "title": "Account ID"},
                "zone_id": {"type": "string", "title": "Zone ID (optional)"},
                "log_types": {
                    "type": "array",
                    "title": "Log Types",
                    "items": {"type": "string", "enum": ["firewall_events", "dns_logs", "http_requests", "audit_logs"]},
                    "default": ["firewall_events", "audit_logs"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["api_token", "account_id"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "RayID",
            "time": "EdgeStartTimestamp",
            "activity_name": "SecurityAction",
            "status_id": {"path": "SecurityAction", "transform": "lower"},
            # Source / client
            "src_endpoint.ip": "ClientIP",
            "src_endpoint.port": {"path": "ClientSrcPort", "transform": "int"},
            "src_endpoint.location.country": "ClientCountry",
            "http_request.user_agent": "ClientRequestUserAgent",
            # Destination / edge
            "dst_endpoint.hostname": "ClientRequestHost",
            "dst_endpoint.ip": "OriginIP",
            # HTTP request / response
            "http_request.url.url_string": "ClientRequestURI",
            "http_request.method": "ClientRequestMethod",
            "http_request.url.scheme": "ClientRequestScheme",
            "http_response.code": {"path": "EdgeResponseStatus", "transform": "int"},
            # Firewall / WAF
            "policy.uid": "SecurityRuleID",
            "policy.name": "SecurityRuleDescription",
            # Traffic
            "network_traffic.bytes_in": {"path": "ClientRequestBytes", "transform": "int"},
            "network_traffic.bytes_out": {"path": "EdgeResponseBodyBytes", "transform": "int"},
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["api_token", "account_id"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {self.config['api_token']}"},
            )
            data = resp.json()
            if data.get("success"):
                return True, "Connection successful"
            return False, str(data.get("errors", "Unknown error"))

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        account_id = self.config["account_id"]
        log_types = self.config.get("log_types", ["audit_logs"])
        headers = {"Authorization": f"Bearer {self.config['api_token']}"}
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            if "audit_logs" in log_types:
                resp = await client.get(
                    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/audit_logs",
                    headers=headers,
                    params={"per_page": 1000},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    audit_events = data.get("result", [])
                    for e in audit_events:
                        e["_log_type"] = "audit_log"
                    events.extend(audit_events)

            if "firewall_events" in log_types:
                zone_id = self.config.get("zone_id")
                if zone_id:
                    resp = await client.get(
                        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/events",
                        headers=headers,
                        params={"per_page": 1000},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        fw_events = data.get("result", [])
                        for e in fw_events:
                            e["_log_type"] = "firewall_event"
                        events.extend(fw_events)

        return events

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        return [payload]
