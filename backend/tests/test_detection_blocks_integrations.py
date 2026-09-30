"""Tests for the destinations and sources added from Detection-blocks.

Vendor APIs are mocked (httpx.MockTransport, a fake boto3 client, a local TCP listener), so these
check the request each integration builds and how it reads responses — not live tenants."""
import asyncio
import json

import httpx
import pytest

from app.connectors.registry import get_connector_class, list_connector_types, load_all_connectors
from app.forwarders.registry import get_forwarder_class, list_forwarder_types, load_all_forwarders

load_all_forwarders()
load_all_connectors()

NEW_DESTINATIONS = [
    "datadog", "new_relic", "grafana_loki", "graylog", "coralogix", "mezmo", "betterstack", "sematext",
    "logicmonitor", "cloudwatch_logs", "azure_monitor_logs", "gcp_logging", "devo", "sentinelone_siem",
    "panther", "opensearch", "syslog", "qradar", "wazuh", "logrhythm", "fortisiem", "manageengine_log360", "trellix_siem",
]
NEW_SOURCES = ["sublime_security", "palo_alto_xsoar", "rapid7_insightidr", "exabeam", "securonix", "hunters", "gurucul"]

EVENTS = [
    {"class_uid": 3002, "class_name": "Authentication", "activity_name": "Logon", "status": "Success",
     "severity_id": 1, "type_uid": 300201, "time": 1790757000000,
     "actor": {"user": {"name": "alice@example.com"}}, "src_endpoint": {"ip": "203.0.113.7"},
     "_raw": {"internal": True}, "_connector_id": "c1"},
    {"class_uid": 3001, "class_name": "Account Change", "activity_name": "Password Reset", "status": "Success",
     "severity_id": 3, "type_uid": 300104, "time": 1790757001000, "user": {"name": "bob"}, "message": "reset|pw=x"},
]


@pytest.fixture
def http(monkeypatch):
    """Route every httpx request to a handler; records requests and serves canned responses."""
    state = {"requests": [], "routes": []}
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        url = str(request.url)
        if "login.microsoftonline.com" in url or "oauth2.googleapis.com" in url:
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
        for needle, status, body in state["routes"]:
            if needle in url:
                if callable(body):
                    body = body(request)
                return httpx.Response(status, **({"text": body} if isinstance(body, str) else {"json": body}))
        return httpx.Response(200, json={})

    def factory(*args, **kwargs):
        kwargs.pop("verify", None)
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    state["route"] = lambda needle, status=200, body=None: state["routes"].append((needle, status, {} if body is None else body))
    return state


def run(coro):
    return asyncio.run(coro)


def forwarder(type_id, config):
    cls = get_forwarder_class(type_id)
    assert cls is not None, type_id
    return cls(forwarder_id="f1", config=config)


def body_of(request):
    return json.loads(request.content)


# ── Registry ────────────────────────────────────────────────────────────────

def test_all_new_integrations_registered_and_marked_beta():
    fwd = {t["type_id"]: t for t in list_forwarder_types()}
    src = {t["type_id"]: t for t in list_connector_types()}
    for t in NEW_DESTINATIONS:
        assert t in fwd, t
        assert fwd[t]["maturity"] == "beta" and fwd[t]["maturity_note"], t
    for t in NEW_SOURCES:
        assert t in src, t
        assert src[t]["maturity"] == "beta" and src[t]["supports_polling"], t
    # Existing integrations keep their stable status
    assert fwd["splunk"]["maturity"] == "stable" and src["okta"]["maturity"] == "stable"


# ── HTTP destinations ───────────────────────────────────────────────────────

HTTP_CASES = [
    ("datadog", {"api_key": "dd", "site": "datadoghq.eu"}, "https://http-intake.logs.datadoghq.eu/api/v2/logs", ("DD-API-KEY", "dd"), 202),
    ("new_relic", {"license_key": "nr", "region": "EU"}, "https://log-api.eu.newrelic.com/log/v1", ("Api-Key", "nr"), 202),
    ("grafana_loki", {"url": "https://loki.example.com/", "username": "u", "password": "p", "tenant_id": "t1"},
     "https://loki.example.com/loki/api/v1/push", ("X-Scope-OrgID", "t1"), 204),
    ("coralogix", {"api_key": "cx", "domain": "eu2.coralogix.com"}, "https://ingress.eu2.coralogix.com/logs/v1/singles", ("Authorization", "Bearer cx"), 200),
    ("mezmo", {"ingestion_key": "mz"}, "https://logs.mezmo.com/logs/ingest", None, 200),
    ("betterstack", {"source_token": "bs"}, "https://in.logs.betterstack.com", ("Authorization", "Bearer bs"), 202),
    ("logicmonitor", {"account": "acme", "bearer_token": "lm"}, "https://acme.logicmonitor.com/rest/log/ingest", ("Authorization", "Bearer lm"), 202),
    ("devo", {"domain": "acme", "token": "dv"}, "https://http-us.devo.io/stream/acme/token!dv/gana/my.app.gana.ocsf", None, 200),
    ("sentinelone_siem", {"url": "https://ingest.us1.sentinelone.net/services/collector/event", "api_key": "s1"},
     "https://ingest.us1.sentinelone.net/services/collector/event", ("Authorization", "Bearer s1"), 200),
    ("panther", {"url": "https://logs.acme.runpanther.net/http/abc", "secret": "sh"}, "https://logs.acme.runpanther.net/http/abc", ("x-panther-secret", "sh"), 200),
    ("azure_monitor_logs", {"tenant_id": "t", "client_id": "c", "client_secret": "s", "dce_endpoint": "https://dce.ingest.monitor.azure.com",
                            "dcr_immutable_id": "dcr-1"},
     "https://dce.ingest.monitor.azure.com/dataCollectionRules/dcr-1/streams/Custom-OCSF_CL?api-version=2023-01-01", ("Authorization", "Bearer tok-123"), 204),
]


@pytest.mark.parametrize("type_id,config,url,header,status", HTTP_CASES, ids=[c[0] for c in HTTP_CASES])
def test_http_destination_sends_both_events(http, type_id, config, url, header, status):
    http["route"](url.split("?")[0], status)
    f = forwarder(type_id, config)
    assert run(f.validate_config())[0]
    assert run(f.forward(EVENTS)) == (2, 0)
    sent = [r for r in http["requests"] if str(r.url).startswith(url.split("?")[0])]
    assert sent, f"no request to {url}"
    assert str(sent[0].url).startswith(url)
    if header:
        assert sent[0].headers.get(header[0]) == header[1]
    # Pipeline-internal fields never leave GANA
    assert b"_connector_id" not in sent[0].content and b'"internal"' not in sent[0].content


def test_http_destination_reports_rejection(http):
    http["route"]("http-intake.logs", 403, {"errors": ["Forbidden"]})
    f = forwarder("datadog", {"api_key": "bad"})
    assert run(f.forward(EVENTS)) == (0, 2)
    ok, msg = run(f.test_connection())
    assert not ok and "403" in msg


def test_datadog_nests_ocsf_to_avoid_reserved_attributes(http):
    http["route"]("http-intake.logs", 202)
    run(forwarder("datadog", {"api_key": "dd"}).forward(EVENTS))
    first = body_of(http["requests"][0])[0]
    assert first["ocsf"]["status"] == "Success" and "status" not in first


def test_loki_groups_streams_by_class_with_nanosecond_timestamps(http):
    http["route"]("/loki/api/v1/push", 204)
    run(forwarder("grafana_loki", {"url": "https://loki"}).forward(EVENTS))
    streams = body_of(http["requests"][0])["streams"]
    assert {s["stream"]["ocsf_class"] for s in streams} == {"Authentication", "Account Change"}
    assert streams[0]["values"][0][0] == str(1790757000000 * 1_000_000)


def test_graylog_sends_flat_gelf_per_event(http):
    http["route"]("/gelf", 202)
    assert run(forwarder("graylog", {"url": "http://graylog:12201"}).forward(EVENTS)) == (2, 0)
    gelf = body_of(http["requests"][0])
    assert gelf["version"] == "1.1" and gelf["_actor_user_name"] == "alice@example.com"
    assert all(k.startswith("_") for k in gelf if k not in ("version", "host", "short_message", "timestamp", "full_message"))


def test_sematext_treats_bulk_item_errors_as_failure(http):
    http["route"]("logsene-receiver", 200, {"errors": True, "items": []})
    assert run(forwarder("sematext", {"app_token": "app"}).forward(EVENTS)) == (0, 2)


def test_panther_hmac_signs_the_body(http):
    import hashlib
    import hmac
    http["route"]("runpanther", 200)
    run(forwarder("panther", {"url": "https://logs.x.runpanther.net/http/1", "auth_method": "hmac",
                              "header_name": "x-sig", "secret": "k"}).forward(EVENTS))
    req = http["requests"][0]
    assert req.headers["x-sig"] == hmac.new(b"k", req.content, hashlib.sha256).hexdigest()


def test_gcp_logging_uses_service_account_token(http):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    sa = json.dumps({"client_email": "gana@p.iam.gserviceaccount.com", "private_key": key})
    http["route"]("logging.googleapis.com", 200)
    assert run(forwarder("gcp_logging", {"project_id": "p", "service_account_json": sa}).forward(EVENTS)) == (2, 0)
    write = [r for r in http["requests"] if "entries:write" in str(r.url)][0]
    body = body_of(write)
    assert write.headers["Authorization"] == "Bearer tok-123"
    assert body["logName"] == "projects/p/logs/gana-ocsf" and body["entries"][1]["severity"] == "WARNING"


def test_cloudwatch_puts_sorted_events(monkeypatch):
    calls = {}

    class AlreadyExists(Exception):
        pass

    class FakeLogs:
        exceptions = type("E", (), {"ResourceAlreadyExistsException": AlreadyExists})

        def create_log_group(self, **kw):
            raise AlreadyExists()

        def create_log_stream(self, **kw):
            calls["stream"] = kw

        def put_log_events(self, **kw):
            calls["put"] = kw
            return {}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeLogs())
    f = forwarder("cloudwatch_logs", {"region": "us-east-1", "log_group": "/g", "log_stream": "s"})
    assert run(f.forward(list(reversed(EVENTS)))) == (2, 0)
    stamps = [e["timestamp"] for e in calls["put"]["logEvents"]]
    assert stamps == sorted(stamps) and calls["stream"] == {"logGroupName": "/g", "logStreamName": "s"}


def test_opensearch_reuses_elasticsearch_bulk(http):
    http["route"]("/_bulk", 200, {"errors": False, "items": []})
    f = forwarder("opensearch", {"url": "https://os.example.com:9200"})
    assert run(f.forward(EVENTS))[0] == 2


# ── Syslog destinations ─────────────────────────────────────────────────────

async def _serve_and_forward(type_id, extra):
    received = []

    async def handle(reader, writer):
        received.append(await reader.read())
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        result = await forwarder(type_id, {"host": "127.0.0.1", "port": port, **extra}).forward(EVENTS)
        await asyncio.sleep(0.2)
    return result, b"".join(received)


@pytest.mark.parametrize("type_id,marker", [("qradar", b"LEEF:2.0|GANA|GANA|1.0|300201|^|"),
                                            ("trellix_siem", b"CEF:0|GANA|GANA|1.0|300201|Authentication|2|"),
                                            ("wazuh", b'"class_uid":3002')])
def test_syslog_presets_send_rfc5424_with_expected_payload(type_id, marker):
    result, data = asyncio.run(_serve_and_forward(type_id, {}))
    lines = data.strip().split(b"\n")
    assert result == (2, 0) and len(lines) == 2
    assert lines[0].startswith(b"<134>1 2026-") and b" gana gana - OCSF - " in lines[0]
    assert marker in lines[0]


def test_syslog_octet_counting_framing():
    result, data = asyncio.run(_serve_and_forward("syslog", {"framing": "octet-counting"}))
    length, rest = data.split(b" ", 1)
    assert result == (2, 0) and int(length) > 0 and rest[:int(length)].endswith(b"}")


def test_syslog_unreachable_collector_counts_failures():
    f = forwarder("syslog", {"host": "127.0.0.1", "port": 1})
    assert run(f.forward(EVENTS)) == (0, 2) and f.last_error


def test_cef_escapes_pipes_and_equals():
    from app.forwarders.syslog import to_cef
    line = to_cef({"class_name": "A|B", "message": "k=v", "type_uid": 1})
    assert "A\\|B" in line and "msg=k\\=v" in line


# ── Alert-platform sources ──────────────────────────────────────────────────

def source(type_id, config):
    cls = get_connector_class(type_id)
    return cls(connector_id="s1", config=config, mapping_rules=cls.meta.default_mapping)


SOURCE_CASES = [
    ("sublime_security", {"api_key": "k", "query": "type.inbound"}, [("/v1/message-groups/query", 200, {"message_groups": [{"id": "mg1", "created_at": "2026-09-30T10:00:00Z"}]})], "mg1"),
    ("rapid7_insightidr", {"api_key": "k", "log_key": "L", "query": "where(x)"}, [("log_search/query/logs/L", 200, {"events": [{"sequence_number_str": "42", "timestamp": 1790757000000}]})], "42"),
    ("exabeam", {"base_url": "https://exa", "client_id": "c", "client_secret": "s", "query": "q"},
     [("/auth/v1/token", 200, {"access_token": "t"}), ("/search/v2/events", 200, {"events": [{"id": "e1", "approxLogTime": "2026-09-30T10:00:00Z"}]})], "e1"),
    ("securonix", {"url": "https://snx", "username": "u", "password": "p", "query": "index=violation"},
     [("/token/generate", 200, "tokenvalue"), ("/spotter/search", 200, {"events": [{"eventid": "v9", "eventtime": 1790757000}]})], "v9"),
    ("hunters", {"base_url": "https://h", "api_token": "t", "query": "q"}, [("/api/search", 200, {"results": [{"id": "lead7", "created_at": "2026-09-30T10:00:00Z"}]})], "lead7"),
    ("gurucul", {"base_url": "https://g", "api_token": "t", "query": "q"}, [("/api/search", 200, {"results": [{"id": "g1", "timestamp": "2026-09-30T10:00:00Z"}]})], "g1"),
    ("palo_alto_xsoar", {"api_url": "https://api-x", "api_key": "k", "api_key_id": "7", "query": "dataset = alerts"},
     [("start_xql_query", 200, {"reply": "qid-1"}),
      ("get_query_results", 200, {"reply": {"status": "SUCCESS", "results": {"data": [{"alert_id": "a1", "_time": 1790757000000}]}}})], "a1"),
]


@pytest.mark.parametrize("type_id,config,routes,expected_id", SOURCE_CASES, ids=[c[0] for c in SOURCE_CASES])
def test_source_pulls_saved_search_and_wraps_rows(http, type_id, config, routes, expected_id):
    for needle, status, body in routes:
        http["route"](needle, status, body)
    events = run(source(type_id, config).fetch_events(since="2026-09-30T09:00:00Z"))
    assert len(events) == 1
    ev = events[0]
    assert ev["result_id"] == expected_id and ev["event_time"].startswith("2026-09-30T") and ev["event_time"].endswith("Z")


def test_source_rows_map_to_detection_finding(http):
    from app.processors.mapper import ocsf_mapper
    http["route"]("/api/search", 200, {"results": [{"id": "lead7", "created_at": "2026-09-30T10:00:00Z", "severity": "high"}]})
    src = source("hunters", {"base_url": "https://h", "api_token": "t", "query": "q", "search_name": "High-risk leads"})
    raw = run(src.fetch_events())[0]
    e = ocsf_mapper.map_event(raw, "s1", "hunters", src.meta.default_mapping, 2004)
    assert (e["class_uid"], e["class_name"], e["type_uid"]) == (2004, "Detection Finding", 200401)
    assert e["finding_info"] == {"uid": "lead7", "title": "High-risk leads", "product_uid": "lead7"}
    from datetime import datetime, timezone
    assert e["time"] == int(datetime(2026, 9, 30, 10, tzinfo=timezone.utc).timestamp() * 1000)
    assert e["metadata"]["product"]["name"] == "Hunters"


def test_source_without_query_is_skipped_not_failed():
    src = source("hunters", {"base_url": "https://h", "api_token": "t"})
    assert src.polling_configured() == (False, "No saved search configured")


def test_source_without_platform_id_gets_stable_hash_id(http):
    http["route"]("/api/search", 200, {"results": [{"title": "no id here", "created_at": "2026-09-30T10:00:00Z"}]})
    src = source("hunters", {"base_url": "https://h", "api_token": "t", "query": "q"})
    a, b = run(src.fetch_events())[0], run(src.fetch_events())[0]
    assert a["result_id"] == b["result_id"] and len(a["result_id"]) == 40


def test_source_http_error_surfaces_in_test_connection(http):
    http["route"]("/api/search", 401, {"error": "bad token"})
    ok, msg = run(source("hunters", {"base_url": "https://h", "api_token": "t", "query": "q"}).test_connection())
    assert not ok and "401" in msg
