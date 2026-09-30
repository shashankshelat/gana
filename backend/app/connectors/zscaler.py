import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class ZscalerConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="zscaler",
        display_name="Zscaler",
        description="Ingest web, firewall, and DNS logs from Zscaler Internet Access (ZIA) API",
        icon="shield",
        category="network",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=4002,
        config_schema={
            "properties": {
                "cloud_name": {"type": "string", "title": "Cloud Name", "placeholder": "zscaler.net"},
                "username": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password", "secret": True},
                "api_key": {"type": "string", "title": "API Key", "secret": True},
                "log_types": {
                    "type": "array",
                    "title": "Log Types",
                    "items": {"type": "string", "enum": ["web", "firewall", "dns", "audit"]},
                    "default": ["web", "firewall"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["cloud_name", "username", "password", "api_key"],
        },
        default_mapping={
            # Core event identity
            "time": "datetime",
            "activity_name": "action",
            "status_id": {"path": "action", "transform": "lower"},
            # Actor / user
            "actor.user.name": "login",
            "actor.user.email_addr": "login",
            "actor.user.domain": "dept",
            # Source endpoint
            "src_endpoint.ip": "cip",
            "src_endpoint.location.country": "location",
            # Destination
            "dst_endpoint.hostname": "ehost",
            "dst_endpoint.ip": "sip",
            "dst_endpoint.port": {"path": "sport", "transform": "int"},
            # HTTP request/response
            "http_request.url.url_string": "eurl",
            "http_request.method": "reqmethod",
            "http_request.user_agent": "ua",
            "http_response.code": {"path": "respcode", "transform": "int"},
            # Traffic size
            "network_traffic.bytes_in": {"path": "respsize", "transform": "int"},
            "network_traffic.bytes_out": {"path": "reqsize", "transform": "int"},
            "network_traffic.proto_name": "proto",
            # Threat / category
            "category.name": "urlcategory",
            "malware.name": "threatname",
            "malware.classification_ids[0]": "malwareclass",
            # File (for download events)
            "file.name": "filename",
            "file.hashes[0].value": "filemd5",
            "file.hashes[0].algorithm_id": "$const:1",
        },
    )

    async def _authenticate(self) -> str:
        import time
        import hashlib

        cloud = self.config["cloud_name"]
        api_key = self.config["api_key"]
        timestamp = str(int(time.time() * 1000))
        obf_key = self._obfuscate_api_key(api_key, timestamp)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://zsapi.{cloud}/api/v1/authenticatedSession",
                json={
                    "username": self.config["username"],
                    "password": self.config["password"],
                    "apiKey": obf_key,
                    "timestamp": timestamp,
                },
            )
            resp.raise_for_status()
            cookies = dict(resp.cookies)
            return cookies.get("JSESSIONID", "")

    def _obfuscate_api_key(self, api_key: str, timestamp: str) -> str:
        seed = timestamp[-6:]
        n = int(seed) >> 1
        char_codes = []
        for i in range(0, 6):
            char_codes.append(ord(api_key[int(seed[i])]))
        for j in range(0, len(seed) - 1):
            char_codes.append(ord(api_key[int(seed[j]) + 2]))
        return "".join(chr(c + n) for c in char_codes)

    async def validate_config(self) -> tuple[bool, str]:
        required = ["cloud_name", "username", "password", "api_key"]
        for field in required:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            session = await self._authenticate()
            if session:
                return True, "Authentication successful"
            return False, "Authentication failed"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        return []
