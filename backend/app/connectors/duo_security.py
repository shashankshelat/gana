import hashlib
import hmac
import time
import base64
import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class DuoSecurityConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="duo_security",
        display_name="Duo Security",
        description="Ingest authentication and administrator activity logs from Duo Security",
        icon="shield",
        category="identity",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "integration_key": {"type": "string", "title": "Integration Key (ikey)"},
                "secret_key": {"type": "string", "title": "Secret Key (skey)", "secret": True},
                "api_hostname": {"type": "string", "title": "API Hostname", "placeholder": "api-XXXXXXXX.duosecurity.com"},
                "log_types": {
                    "type": "array",
                    "title": "Log Types",
                    "items": {"type": "string", "enum": ["authentication", "administrator", "telephony"]},
                    "default": ["authentication"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 60},
            },
            "required": ["integration_key", "secret_key", "api_hostname"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "txid",
            "time": "isotimestamp",
            "activity_name": "event_type",
            "status_id": {"path": "result", "transform": "lower"},
            "status_detail": "reason",
            # Actor / user
            "actor.user.uid": "user.key",
            "actor.user.name": "user.name",
            "actor.user.email_addr": "user.email",
            # Access device (source)
            "src_endpoint.ip": "access_device.ip",
            "src_endpoint.location.city": "access_device.location.city",
            "src_endpoint.location.country": "access_device.location.country",
            "http_request.user_agent": "access_device.browser",
            "src_endpoint.os": "access_device.os",
            # Auth device (MFA device)
            "device.uid": "auth_device.key",
            "device.name": "auth_device.name",
            "device.type": "auth_device.type",
            # Application accessed
            "app_name": "application.name",
            "app_uid": "application.key",
            # MFA factor
            "auth_protocol": "factor",
        },
    )

    def _sign_request(self, method: str, host: str, path: str, params: dict) -> dict:
        now = str(int(time.time()))
        canon_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        canon = "\n".join([now, method.upper(), host.lower(), path, canon_params])
        sig = hmac.new(self.config["secret_key"].encode(), canon.encode(), hashlib.sha1).hexdigest()
        auth = base64.b64encode(f"{self.config['integration_key']}:{sig}".encode()).decode()
        return {"Date": now, "Authorization": f"Basic {auth}"}

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["integration_key", "secret_key", "api_hostname"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        host = self.config["api_hostname"]
        path = "/admin/v1/info/authentication_attempts"
        headers = self._sign_request("GET", host, path, {})
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"https://{host}{path}", headers=headers)
                if resp.status_code in (200, 401):
                    return True, "Connected to Duo API"
                return False, f"HTTP {resp.status_code}"
            except Exception as e:
                return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        host = self.config["api_hostname"]
        log_types = self.config.get("log_types", ["authentication"])
        min_time = int(time.time()) - 3600
        events = []

        async with httpx.AsyncClient(timeout=30) as client:
            for log_type in log_types:
                if log_type == "authentication":
                    path = "/admin/v2/logs/authentication"
                    params = {"mintime": str(min_time), "limit": "1000"}
                elif log_type == "administrator":
                    path = "/admin/v1/logs/administrator"
                    params = {"mintime": str(min_time)}
                else:
                    continue

                headers = self._sign_request("GET", host, path, params)
                resp = await client.get(f"https://{host}{path}", headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("response", {}).get("authlogs", data.get("response", []))
                    if isinstance(items, list):
                        for item in items:
                            item["_log_type"] = log_type
                        events.extend(items)
        return events
