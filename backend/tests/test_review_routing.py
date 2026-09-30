"""Mapping-status stamping and routing of unclassified events to each forwarder's review destination."""
import asyncio
import json

import httpx
import pytest

from app.forwarders.registry import get_forwarder_class, load_all_forwarders
from app.processors.mapper import MAPPING_LABEL, mapping_status, stamp_mapping_status

load_all_forwarders()


def run(coro):
    return asyncio.run(coro)


def forwarder(type_id, config):
    return get_forwarder_class(type_id)(forwarder_id="f1", config=config)


def event(status, class_uid=3002, class_name="Authentication"):
    e = {"class_uid": class_uid, "class_name": class_name, "time": 1790757000000, "metadata": {"labels": ["keep"]}}
    stamp_mapping_status(e, status)
    return e


CLASSIFIED, UNCLASSIFIED, UNVERIFIED = event("classified"), event("unclassified", 0, "Base Event"), event("unverified")


def test_mapping_status():
    routes = {"_routes": [{"when": {}}]}
    assert mapping_status(routes, {"class_uid": 3002}, 3002) == "classified"
    assert mapping_status(routes, None, 3002) == "unclassified"   # routes exist but none matched
    assert mapping_status({}, None, 0) == "unclassified"          # Base Event
    assert mapping_status({}, None, 3002) == "unverified"         # single-class mapping, no routes


def test_stamp_replaces_previous_label():
    e = event("unverified")
    stamp_mapping_status(e, "classified")
    assert e["metadata"]["labels"] == ["keep", f"{MAPPING_LABEL}classified"]
    assert e["_mapping_status"] == "classified"


@pytest.fixture
def posts(monkeypatch):
    sent = []
    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw.pop("verify", None)
        kw["transport"] = httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200, json={"errors": False, "items": []}))[1])
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return sent


def test_splunk_splits_requests_by_index(posts):
    f = forwarder("splunk", {"hec_url": "https://splunk:8088", "hec_token": "t", "index": "main", "review_index": "ocsf_review"})
    assert run(f.forward([CLASSIFIED, UNCLASSIFIED, UNVERIFIED])) == (3, 0)
    indexes = [{json.loads(line)["index"] for line in r.content.decode().replace("}{", "}\n{").splitlines()} for r in posts]
    assert sorted(map(sorted, indexes)) == [["main"], ["ocsf_review"]]


def test_splunk_unverified_opt_in_and_blank_review_index():
    on = forwarder("splunk", {"index": "main", "review_index": "rev", "review_include_unverified": True})
    assert on._hec_event(UNVERIFIED)["index"] == "rev"
    off = forwarder("splunk", {"index": "main", "review_index": ""})
    assert off._hec_event(UNCLASSIFIED)["index"] == "main"


def test_elasticsearch_review_pattern():
    f = forwarder("elasticsearch", {"url": "http://es", "review_index_pattern": "ocsf-review-{class_name}"})
    assert f._resolve_index(UNCLASSIFIED) == "ocsf-review-base-event"
    assert f._resolve_index(CLASSIFIED).startswith("ocsf-authentication-")


def test_gcp_review_log_name():
    f = forwarder("gcp_logging", {"project_id": "p", "log_id": "main", "review_log_id": "rev"})
    assert f._entry(UNCLASSIFIED, "p")["logName"] == "projects/p/logs/rev"
    assert "logName" not in f._entry(CLASSIFIED, "p")


def test_cloudwatch_review_stream(monkeypatch):
    puts = []

    class Exists(Exception):
        pass

    class FakeLogs:
        exceptions = type("E", (), {"ResourceAlreadyExistsException": Exists})

        def create_log_group(self, **kw):
            raise Exists()

        def create_log_stream(self, **kw):
            pass

        def put_log_events(self, **kw):
            puts.append((kw["logStreamName"], len(kw["logEvents"])))
            return {}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeLogs())
    f = forwarder("cloudwatch_logs", {"region": "us-east-1", "log_group": "/g", "log_stream": "main", "review_log_stream": "rev"})
    assert run(f.forward([CLASSIFIED, UNCLASSIFIED, UNVERIFIED])) == (3, 0)
    assert sorted(puts) == [("main", 2), ("rev", 1)]


def test_s3_review_prefix(monkeypatch):
    keys = []

    class FakeS3:
        def put_object(self, **kw):
            keys.append((kw["Key"], kw["Metadata"]["ocsf-event-count"]))

    f = forwarder("s3", {"bucket": "b", "prefix": "ocsf/events/", "review_prefix": "ocsf/review/"})
    monkeypatch.setattr(f, "_get_s3_client", lambda: FakeS3())
    assert run(f.forward([CLASSIFIED, UNCLASSIFIED])) == (2, 0)
    assert sorted((k.split("/")[1], n) for k, n in keys) == [("events", "1"), ("review", "1")]
