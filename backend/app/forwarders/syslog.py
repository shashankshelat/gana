"""Syslog destination (RFC 5424 over UDP/TCP/TLS; JSON, CEF or LEEF payloads) and SIEM presets.

Classic SIEMs (QRadar, Wazuh, LogRhythm, FortiSIEM, ManageEngine Log360, Trellix ESM) take
third-party logs through syslog collectors, so these presets are the same forwarder with the
payload format and port each product expects by default."""
import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone

from app.forwarders._common import BETA_NOTE, clean_event, event_summary, event_time_ms, flatten
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder

logger = logging.getLogger(__name__)

# OCSF severity_id → syslog severity (0 emerg … 7 debug)
_SYSLOG_SEV = {0: 6, 1: 6, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1}


def _base_schema(port: int, fmt: str, protocol: str = "tcp") -> dict:
    return {
        "properties": {
            "host": {"type": "string", "title": "Collector host"},
            "port": {"type": "integer", "title": "Port", "default": port},
            "protocol": {"type": "string", "title": "Protocol", "default": protocol, "enum": ["tcp", "udp", "tls"]},
            "format": {"type": "string", "title": "Payload format", "default": fmt, "enum": ["json", "cef", "leef"]},
            "facility": {"type": "integer", "title": "Facility (16 = local0)", "default": 16},
            "app_name": {"type": "string", "title": "APP-NAME", "default": "gana"},
            "framing": {"type": "string", "title": "TCP framing", "default": "newline", "enum": ["newline", "octet-counting"]},
            "verify_ssl": {"type": "boolean", "title": "Verify TLS certificate", "default": True},
        },
        "required": ["host"],
    }


def _cef_escape_header(v) -> str:
    return str(v).replace("\\", "\\\\").replace("|", "\\|")


def _cef_escape_ext(v) -> str:
    return str(v).replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n").replace("\r", "\\r")


def _pick(e: dict, *paths):
    for p in paths:
        cur = e
        for part in p.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, ""):
            return cur
    return None


def to_cef(e: dict) -> str:
    ext = {
        "rt": event_time_ms(e),
        "msg": event_summary(e),
        "act": e.get("activity_name"),
        "outcome": e.get("status"),
        "suser": _pick(e, "actor.user.name", "actor.user.email_addr"),
        "duser": _pick(e, "user.name", "user.email_addr"),
        "src": _pick(e, "src_endpoint.ip"),
        "dst": _pick(e, "dst_endpoint.ip"),
        "cs1Label": "ocsf_class_uid", "cs1": e.get("class_uid"),
        "cs2Label": "ocsf_event", "cs2": json.dumps(e, default=str, separators=(",", ":")),
    }
    sev = min(10, int(e.get("severity_id") or 0) * 2)
    header = "|".join(_cef_escape_header(x) for x in (
        "CEF:0", "GANA", "GANA", "1.0", e.get("type_uid", 0), e.get("class_name") or "OCSF event", sev))
    return header + "|" + " ".join(f"{k}={_cef_escape_ext(v)}" for k, v in ext.items() if v not in (None, ""))


def to_leef(e: dict) -> str:
    fields = {
        "cat": e.get("class_name"),
        "sev": min(10, int(e.get("severity_id") or 0) * 2),
        "usrName": _pick(e, "actor.user.name", "user.name"),
        "src": _pick(e, "src_endpoint.ip"),
        "dst": _pick(e, "dst_endpoint.ip"),
        "ocsfActivity": e.get("activity_name"),
        "ocsfStatus": e.get("status"),
        "msg": event_summary(e),
    }
    # Remaining OCSF attributes flattened as custom LEEF keys (dots are not allowed in key names)
    for k, v in flatten(e).items():
        fields.setdefault(k, v)
    body = "^".join(f"{k}={str(v).replace('^', ' ').replace(chr(10), ' ')}" for k, v in fields.items() if v not in (None, ""))
    return f"LEEF:2.0|GANA|GANA|1.0|{e.get('type_uid', 0)}|^|{body}"


class SyslogForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="syslog", display_name="Syslog (RFC 5424)",
        description="Send OCSF events to any syslog collector over UDP, TCP or TLS, as JSON, CEF or LEEF",
        icon="syslog", category="siem", max_batch_size=1000, maturity="beta",
        maturity_note="Standards-based (RFC 5424); tested against a local TCP listener, not a specific SIEM.",
        config_schema=_base_schema(514, "json"),
    )

    async def validate_config(self) -> tuple[bool, str]:
        return (True, "") if self.config.get("host") else (False, "host is required")

    def _message(self, e: dict) -> bytes:
        fmt = self.config.get("format") or self.meta.config_schema["properties"]["format"]["default"]
        payload = to_cef(e) if fmt == "cef" else to_leef(e) if fmt == "leef" else json.dumps(e, default=str, separators=(",", ":"))
        pri = int(self.config.get("facility") or 16) * 8 + _SYSLOG_SEV.get(e.get("severity_id"), 6)
        ts = datetime.fromtimestamp(event_time_ms(e) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return f"<{pri}>1 {ts} gana {self.config.get('app_name') or 'gana'} - OCSF - {payload}".encode()

    def _frame(self, msg: bytes) -> bytes:
        if (self.config.get("framing") or "newline") == "octet-counting":
            return f"{len(msg)} ".encode() + msg
        return msg + b"\n"

    async def forward(self, events):
        self.last_error = ""
        host = self.config["host"]
        port = int(self.config.get("port") or self.meta.config_schema["properties"]["port"]["default"])
        protocol = self.config.get("protocol") or "tcp"
        messages = [self._message(clean_event(e)) for e in events]
        try:
            if protocol == "udp":
                loop = asyncio.get_running_loop()
                transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, remote_addr=(host, port))
                try:
                    for m in messages:
                        transport.sendto(m)
                finally:
                    transport.close()
                # UDP gives no delivery signal; count datagrams handed to the network
                return len(messages), 0
            ssl_ctx = None
            if protocol == "tls":
                ssl_ctx = ssl.create_default_context()
                if not self.config.get("verify_ssl", True):
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = ssl.CERT_NONE
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ssl_ctx), timeout=15)
            try:
                writer.write(b"".join(self._frame(m) for m in messages))
                await asyncio.wait_for(writer.drain(), timeout=30)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            return len(messages), 0
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            logger.error("%s forwarder %s: %s", self.meta.type_id, self.forwarder_id, self.last_error)
            return 0, len(messages)

    async def test_connection(self) -> tuple[bool, str]:
        ok, msg = await self.validate_config()
        if not ok:
            return False, msg
        success, _ = await self.forward([{"class_uid": 0, "class_name": "Base Event", "message": "GANA connection test"}])
        if success:
            return True, f"Test message sent to {self.config['host']}:{self.config.get('port') or self.meta.config_schema['properties']['port']['default']}"
        return False, self.last_error or "Could not send the test message"


register_forwarder(SyslogForwarder)


def _preset(type_id: str, name: str, fmt: str, port: int, how: str):
    cls = type(f"{type_id.title().replace('_', '')}SyslogForwarder", (SyslogForwarder,), {
        "meta": ForwarderMeta(
            type_id=type_id, display_name=name,
            description=f"Send OCSF events to {name} over syslog ({fmt.upper()}). {how}",
            icon=type_id, category="siem", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
            config_schema=_base_schema(port, fmt),
        ),
    })
    return register_forwarder(cls)


_preset("qradar", "IBM QRadar", "leef", 514,
        "QRadar auto-detects LEEF; or add a Universal LEEF log source for the GANA host.")
_preset("wazuh", "Wazuh", "json", 514,
        "Enable a syslog <remote> block in the manager's ossec.conf (TCP, allowed-ips = GANA); Wazuh's JSON decoder parses the payload.")
_preset("logrhythm", "LogRhythm SIEM", "json", 514,
        "Point it at a System Monitor / Open Collector syslog listener and add a JSON parsing rule.")
_preset("fortisiem", "FortiSIEM", "cef", 514,
        "FortiSIEM collectors parse CEF over syslog; register GANA as a reporting device.")
_preset("manageengine_log360", "ManageEngine Log360", "json", 514,
        "Add GANA as a syslog device in Log360 / EventLog Analyzer and import a JSON log format.")
_preset("trellix_siem", "Trellix SIEM (ESM)", "cef", 514,
        "Add a CEF syslog data source for the GANA host on the Event Receiver.")
