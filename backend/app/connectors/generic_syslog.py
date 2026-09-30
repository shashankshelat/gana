import asyncio
import logging
import re
from datetime import datetime, timezone

from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector

logger = logging.getLogger(__name__)

RFC5424_PATTERN = re.compile(
    r"<(?P<priority>\d+)>(?P<version>\d+)\s+"
    r"(?P<timestamp>\S+)\s+(?P<hostname>\S+)\s+"
    r"(?P<app_name>\S+)\s+(?P<procid>\S+)\s+(?P<msgid>\S+)\s+"
    r"(?P<structured_data>\[.*?\]|-)\s*(?P<message>.*)",
    re.DOTALL,
)

RFC3164_PATTERN = re.compile(
    r"<(?P<priority>\d+)>(?P<timestamp>\w{3}\s+\d+\s+\d+:\d+:\d+)\s+"
    r"(?P<hostname>\S+)\s+(?P<app_name>\S+?)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)",
    re.DOTALL,
)


@register_connector
class GenericSyslogConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="generic_syslog",
        display_name="Generic Syslog",
        description="Receive syslog messages (RFC3164/RFC5424) over UDP or TCP",
        icon="terminal",
        category="custom",
        auth_methods=["certificate"],
        supports_streaming=True,
        default_ocsf_class_uid=0,  # unknown logs: Base Event until routes classify them
        config_schema={
            "properties": {
                "port": {"type": "integer", "title": "Listen Port", "default": 514},
                "protocol": {"type": "string", "title": "Protocol", "enum": ["udp", "tcp"], "default": "udp"},
                "format": {
                    "type": "string",
                    "title": "Syslog Format",
                    "enum": ["auto", "rfc3164", "rfc5424", "json"],
                    "default": "auto",
                },
                "tls_enabled": {"type": "boolean", "title": "Enable TLS", "default": False},
                "bind_address": {"type": "string", "title": "Bind Address", "default": "0.0.0.0"},
            },
        },
        default_mapping={
            "time": "_parsed_time",
            "src_endpoint.hostname": "_hostname",
            "app_name": "_app_name",
            "message": "_message",
            "severity_id": "_severity_id",
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        port = self.config.get("port", 514)
        if not (1 <= int(port) <= 65535):
            return False, "port must be between 1 and 65535"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        return True, f"Syslog listener ready on port {self.config.get('port', 514)}"

    def parse_syslog(self, raw: str) -> dict:
        fmt = self.config.get("format", "auto")

        if fmt == "json" or (fmt == "auto" and raw.strip().startswith("{")):
            import json
            try:
                return json.loads(raw)
            except Exception:
                pass

        match = RFC5424_PATTERN.match(raw)
        if match and (fmt in ("auto", "rfc5424")):
            g = match.groupdict()
            priority = int(g["priority"])
            return {
                "_hostname": g["hostname"],
                "_app_name": g["app_name"],
                "_message": g["message"],
                "_parsed_time": g["timestamp"],
                "_severity_id": priority & 7,
                "_facility": priority >> 3,
                "_procid": g["procid"],
                "_msgid": g["msgid"],
                "_raw": raw,
            }

        match = RFC3164_PATTERN.match(raw)
        if match and (fmt in ("auto", "rfc3164")):
            g = match.groupdict()
            priority = int(g["priority"])
            return {
                "_hostname": g["hostname"],
                "_app_name": g["app_name"],
                "_message": g["message"],
                "_parsed_time": g["timestamp"],
                "_severity_id": priority & 7,
                "_facility": priority >> 3,
                "_raw": raw,
            }

        return {"_raw": raw, "_message": raw, "_parsed_time": datetime.now(timezone.utc).isoformat()}
