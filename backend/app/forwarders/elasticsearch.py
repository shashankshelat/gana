import json
import httpx
from app.forwarders.base import BaseForwarder, ForwarderMeta, review_fields
from app.forwarders.registry import register_forwarder


@register_forwarder
class ElasticsearchForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="elasticsearch",
        display_name="Elasticsearch / OpenSearch",
        description="Forward OCSF events to Elasticsearch or OpenSearch via Bulk API",
        icon="elasticsearch",
        category="siem",
        max_batch_size=5000,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "Elasticsearch URL", "placeholder": "https://es.example.com:9200"},
                "username": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password", "secret": True},
                "api_key": {"type": "string", "title": "API Key (alternative to user/pass)", "secret": True},
                "index_pattern": {"type": "string", "title": "Index Pattern", "default": "ocsf-{class_name}-{date}"},
                **review_fields("review_index_pattern", "Review index pattern for unclassified events (blank = same)", "ocsf-review-{date}"),
                "pipeline": {"type": "string", "title": "Ingest Pipeline (optional)"},
                "verify_ssl": {"type": "boolean", "title": "Verify SSL", "default": True},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["url"],
        },
    )

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/x-ndjson"}
        if self.config.get("api_key"):
            headers["Authorization"] = f"ApiKey {self.config['api_key']}"
        return headers

    def _get_auth(self):
        if self.config.get("username"):
            return (self.config["username"], self.config.get("password", ""))
        return None

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("url"):
            return False, "url is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        base_url = self.config["url"].rstrip("/")
        verify = self.config.get("verify_ssl", True)
        async with httpx.AsyncClient(timeout=10, verify=verify) as client:
            try:
                resp = await client.get(
                    f"{base_url}/_cluster/health",
                    headers=self._get_headers(),
                    auth=self._get_auth(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return True, f"Cluster {data.get('cluster_name')} is {data.get('status')}"
                return False, f"HTTP {resp.status_code}"
            except Exception as e:
                return False, str(e)

    def _resolve_index(self, event: dict) -> str:
        from datetime import datetime, timezone
        pattern = self.config.get("index_pattern", "ocsf-{class_name}-{date}")
        if self.config.get("review_index_pattern") and self.is_review(event):
            pattern = self.config["review_index_pattern"]
        class_name = event.get("class_name", "events").lower().replace(" ", "-")
        date = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        return pattern.format(class_name=class_name, date=date)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        base_url = self.config["url"].rstrip("/")
        verify = self.config.get("verify_ssl", True)
        batch_size = self.config.get("batch_size", 500)
        pipeline = self.config.get("pipeline", "")

        success = 0
        failed = 0

        async with httpx.AsyncClient(timeout=60, verify=verify) as client:
            for i in range(0, len(events), batch_size):
                batch = events[i:i + batch_size]
                bulk_lines = []
                for event in batch:
                    index_name = self._resolve_index(event)
                    action = {"index": {"_index": index_name}}
                    if event.get("metadata", {}).get("uid"):
                        action["index"]["_id"] = event["metadata"]["uid"]
                    bulk_lines.append(json.dumps(action))
                    clean_event = {k: v for k, v in event.items() if not k.startswith("_")}
                    bulk_lines.append(json.dumps(clean_event))

                payload = "\n".join(bulk_lines) + "\n"
                url = f"{base_url}/_bulk"
                if pipeline:
                    url += f"?pipeline={pipeline}"

                try:
                    resp = await client.post(
                        url,
                        content=payload,
                        headers=self._get_headers(),
                        auth=self._get_auth(),
                    )
                    if resp.status_code in (200, 201):
                        resp_data = resp.json()
                        if resp_data.get("errors"):
                            for item in resp_data.get("items", []):
                                idx = item.get("index", {})
                                if idx.get("status", 200) >= 400:
                                    failed += 1
                                else:
                                    success += 1
                        else:
                            success += len(batch)
                    else:
                        failed += len(batch)
                except Exception:
                    failed += len(batch)

        return success, failed
