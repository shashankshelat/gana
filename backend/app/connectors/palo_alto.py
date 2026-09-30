import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


@register_connector
class PaloAltoConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="palo_alto",
        display_name="Palo Alto Networks",
        description="Ingest threat, traffic, and audit logs from Palo Alto NGFW or Cortex Data Lake",
        icon="shield",
        category="network",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=4001,
        config_schema={
            "properties": {
                "source": {
                    "type": "string",
                    "title": "Source",
                    "enum": ["cortex_data_lake", "ngfw"],
                    "default": "cortex_data_lake",
                },
                "api_key": {"type": "string", "title": "API Key", "secret": True},
                "cortex_fqdn": {"type": "string", "title": "Cortex FQDN", "placeholder": "api.us.cdl.paloaltonetworks.com"},
                "ngfw_host": {"type": "string", "title": "NGFW Host/IP"},
                "log_types": {
                    "type": "array",
                    "title": "Log Types",
                    "items": {"type": "string", "enum": ["threat", "traffic", "auth", "audit"]},
                    "default": ["threat", "traffic"],
                },
            },
            "required": ["api_key"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "seqno",
            "time": "receive_time",
            "activity_name": "subtype",
            "severity_id": {"path": "severity", "transform": "lower"},
            "status_id": {"path": "action", "transform": "lower"},
            # Network traffic
            "src_endpoint.ip": "src",
            "src_endpoint.port": {"path": "sport", "transform": "int"},
            "src_endpoint.location.country": "srcloc",
            "src_endpoint.interface_uid": "inbound_if",
            "dst_endpoint.ip": "dst",
            "dst_endpoint.port": {"path": "dport", "transform": "int"},
            "dst_endpoint.location.country": "dstloc",
            "dst_endpoint.interface_uid": "outbound_if",
            "network_traffic.proto_name": "proto",
            "network_traffic.bytes": {"path": "bytes", "transform": "int"},
            "network_traffic.bytes_in": {"path": "bytes_received", "transform": "int"},
            "network_traffic.bytes_out": {"path": "bytes_sent", "transform": "int"},
            "network_traffic.packets": {"path": "packets", "transform": "int"},
            # Application / zones
            "app_name": "app",
            "src_endpoint.zone": "from",
            "dst_endpoint.zone": "to",
            # Policy / rule
            "policy.name": "rule",
            "policy.uid": "ruleuuid",
            # Actor
            "actor.user.name": "srcuser",
            # Threat
            "malware.name": "threatid",
            "category.name": "category",
            # Device
            "device.hostname": "device_name",
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("api_key"):
            return False, "api_key is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        host = self.config.get("ngfw_host")
        if not host:
            return True, "Configuration saved (cannot test Cortex without active connection)"
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            try:
                resp = await client.get(
                    f"https://{host}/api/?type=version&key={self.config['api_key']}"
                )
                if resp.status_code == 200:
                    return True, "Connected to NGFW"
                return False, f"HTTP {resp.status_code}"
            except Exception as e:
                return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        host = self.config.get("ngfw_host")
        if not host:
            return []
        log_types = self.config.get("log_types", ["threat"])
        events = []
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            for log_type in log_types:
                resp = await client.get(
                    f"https://{host}/api/",
                    params={
                        "type": "log",
                        "log-type": log_type,
                        "key": self.config["api_key"],
                        "nlogs": 1000,
                    },
                )
                if resp.status_code == 200:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(resp.text)
                    for entry in root.findall(".//entry"):
                        event = {child.tag: child.text for child in entry}
                        event["_log_type"] = log_type
                        events.append(event)
        return events
