"""Cloud provider log services as destinations: AWS CloudWatch Logs, Azure Monitor Logs, Google Cloud Logging."""
import asyncio
import json

from app.forwarders._common import (
    BETA_NOTE, HttpBatchForwarder, azure_ad_token, chunks, clean_event, event_time_iso, event_time_ms, google_sa_token,
)
from app.forwarders.base import ForwarderMeta, review_fields
from app.forwarders.registry import register_forwarder


@register_forwarder
class CloudWatchLogsForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="cloudwatch_logs", display_name="AWS CloudWatch Logs",
        description="Write OCSF events to a CloudWatch Logs group/stream with PutLogEvents",
        icon="aws", category="cloud", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "region": {"type": "string", "title": "AWS Region", "default": "us-east-1"},
                "log_group": {"type": "string", "title": "Log Group", "default": "/gana/ocsf"},
                "log_stream": {"type": "string", "title": "Log Stream", "default": "gana"},
                **review_fields("review_log_stream", "Review log stream for unclassified events (blank = same)", "gana-review"),
                "access_key_id": {"type": "string", "title": "Access Key ID (blank = default credential chain)"},
                "secret_access_key": {"type": "string", "title": "Secret Access Key", "secret": True},
                "create_if_missing": {"type": "boolean", "title": "Create group/stream if missing", "default": True},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 1000},
            },
            "required": ["region", "log_group", "log_stream"],
        },
    )

    def _client(self):
        import boto3
        kwargs = {"region_name": self.config.get("region") or "us-east-1"}
        if self.config.get("access_key_id"):
            kwargs.update(aws_access_key_id=self.config["access_key_id"],
                          aws_secret_access_key=self.config.get("secret_access_key", ""))
        return boto3.client("logs", **kwargs)

    def _ensure_stream(self, client, stream: str):
        group = self.config["log_group"]
        for create, kwargs in ((client.create_log_group, {"logGroupName": group}),
                               (client.create_log_stream, {"logGroupName": group, "logStreamName": stream})):
            try:
                create(**kwargs)
            except client.exceptions.ResourceAlreadyExistsException:
                pass

    def _put(self, events: list[dict]) -> tuple[int, int]:
        client = self._client()
        main_stream = self.config["log_stream"]
        review_stream = self.config.get("review_log_stream")
        by_stream: dict[str, list[dict]] = {}
        for e in events:
            stream = review_stream if review_stream and self.is_review(e) else main_stream
            by_stream.setdefault(stream, []).append(e)
        success = failed = 0
        for stream, group in by_stream.items():
            if self.config.get("create_if_missing", True):
                self._ensure_stream(client, stream)
            # PutLogEvents needs chronological order; the API caps a call at 10,000 events / 1 MB
            records = sorted(({"timestamp": event_time_ms(e), "message": json.dumps(clean_event(e), default=str)}
                              for e in group), key=lambda r: r["timestamp"])
            for batch in chunks(records, int(self.config.get("batch_size") or 1000)):
                try:
                    resp = client.put_log_events(logGroupName=self.config["log_group"], logStreamName=stream, logEvents=batch)
                    rejected = resp.get("rejectedLogEventsInfo") or {}
                    bad = len(batch) if rejected else 0
                    if rejected:
                        self.last_error = f"CloudWatch rejected events: {rejected}"
                    success += len(batch) - bad
                    failed += bad
                except Exception as e:
                    failed += len(batch)
                    self.last_error = f"{type(e).__name__}: {e}"
        return success, failed

    async def forward(self, events):
        self.last_error = ""
        # boto3 is synchronous; keep it off the event loop
        return await asyncio.to_thread(self._put, events)


@register_forwarder
class AzureMonitorLogsForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="azure_monitor_logs", display_name="Azure Monitor Logs (Logs Ingestion API)",
        description="Send OCSF events to a Log Analytics custom table through a Data Collection Rule. "
                    "The DCR stream needs columns TimeGenerated (datetime), ClassUid (int), ClassName (string), Event (dynamic).",
        icon="azure", category="cloud", max_batch_size=500, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "tenant_id": {"type": "string", "title": "Tenant ID"},
                "client_id": {"type": "string", "title": "App (client) ID"},
                "client_secret": {"type": "string", "title": "Client Secret", "secret": True},
                "dce_endpoint": {"type": "string", "title": "Data Collection Endpoint", "placeholder": "https://my-dce.eastus-1.ingest.monitor.azure.com"},
                "dcr_immutable_id": {"type": "string", "title": "DCR Immutable ID", "placeholder": "dcr-…"},
                "stream_name": {"type": "string", "title": "Stream name", "default": "Custom-OCSF_CL"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 200},
            },
            "required": ["tenant_id", "client_id", "client_secret", "dce_endpoint", "dcr_immutable_id"],
        },
    )

    async def _request(self, batch):
        token = await azure_ad_token(self.config["tenant_id"], self.config["client_id"],
                                     self.config["client_secret"], "https://monitor.azure.com/.default")
        stream = self.config.get("stream_name") or "Custom-OCSF_CL"
        return {
            "method": "POST",
            "url": f"{self.config['dce_endpoint'].rstrip('/')}/dataCollectionRules/{self.config['dcr_immutable_id']}"
                   f"/streams/{stream}",
            "params": {"api-version": "2023-01-01"},
            "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            "json": [{"TimeGenerated": event_time_iso(e), "ClassUid": e.get("class_uid"),
                      "ClassName": e.get("class_name"), "Event": e} for e in batch],
        }


@register_forwarder
class GCPLoggingForwarder(HttpBatchForwarder):
    meta = ForwarderMeta(
        type_id="gcp_logging", display_name="Google Cloud Logging",
        description="Write OCSF events to Cloud Logging with entries.write (jsonPayload)",
        icon="gcp", category="cloud", max_batch_size=1000, maturity="beta", maturity_note=BETA_NOTE,
        config_schema={
            "properties": {
                "project_id": {"type": "string", "title": "Project ID"},
                "service_account_json": {"type": "string", "title": "Service Account JSON (roles/logging.logWriter)", "secret": True, "multiline": True},
                "log_id": {"type": "string", "title": "Log ID", "default": "gana-ocsf"},
                **review_fields("review_log_id", "Review log ID for unclassified events (blank = same)", "gana-ocsf-review"),
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["project_id", "service_account_json"],
        },
    )

    _severity = {0: "DEFAULT", 1: "INFO", 2: "NOTICE", 3: "WARNING", 4: "ERROR", 5: "CRITICAL", 6: "EMERGENCY"}

    def _entry(self, e: dict, project: str) -> dict:
        entry = {"timestamp": event_time_iso(e), "severity": self._severity.get(e.get("severity_id"), "DEFAULT"),
                 "labels": {"ocsf_class": str(e.get("class_name") or ""), "gana_mapping": e.get("_mapping_status", "")},
                 "jsonPayload": clean_event(e)}
        if self.config.get("review_log_id") and self.is_review(e):
            entry["logName"] = f"projects/{project}/logs/{self.config['review_log_id']}"
        return entry

    async def _request(self, batch):
        token = await google_sa_token(self.config["service_account_json"], "https://www.googleapis.com/auth/logging.write")
        project = self.config["project_id"]
        return {
            "method": "POST",
            "url": "https://logging.googleapis.com/v2/entries:write",
            "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            "json": {
                "logName": f"projects/{project}/logs/{self.config.get('log_id') or 'gana-ocsf'}",
                "resource": {"type": "global", "labels": {"project_id": project}},
                "partialSuccess": True,
                "entries": [self._entry(e, project) for e in batch],
            },
        }
