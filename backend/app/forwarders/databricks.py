import json
import httpx
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder


@register_forwarder
class DatabricksForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="databricks",
        display_name="Databricks",
        description="Forward OCSF events to Databricks Delta Lake via REST API or Auto Loader",
        icon="databricks",
        category="data_lake",
        max_batch_size=10000,
        config_schema={
            "properties": {
                "workspace_url": {"type": "string", "title": "Workspace URL", "placeholder": "https://adb-xxxx.azuredatabricks.net"},
                "token": {"type": "string", "title": "Personal Access Token", "secret": True},
                "catalog": {"type": "string", "title": "Unity Catalog Name", "default": "main"},
                "schema": {"type": "string", "title": "Schema/Database", "default": "security"},
                "table": {"type": "string", "title": "Table Name", "default": "ocsf_events"},
                "checkpoint_path": {"type": "string", "title": "Checkpoint Path", "default": "/tmp/ocsf_checkpoint"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 1000},
                "ingestion_method": {
                    "type": "string",
                    "title": "Ingestion Method",
                    "enum": ["rest_api", "delta_sharing", "s3_staging"],
                    "default": "rest_api",
                },
            },
            "required": ["workspace_url", "token"],
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["workspace_url", "token"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        url = self.config["workspace_url"].rstrip("/")
        token = self.config["token"]
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{url}/api/2.0/clusters/list",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return True, "Connected to Databricks workspace"
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        method = self.config.get("ingestion_method", "rest_api")
        if method == "rest_api":
            return await self._forward_via_api(events)
        return await self._forward_via_api(events)

    async def _forward_via_api(self, events: list[dict]) -> tuple[int, int]:
        url = self.config["workspace_url"].rstrip("/")
        token = self.config["token"]
        catalog = self.config.get("catalog", "main")
        schema = self.config.get("schema", "security")
        table = self.config.get("table", "ocsf_events")
        full_table = f"{catalog}.{schema}.{table}"

        rows = [json.dumps(e) for e in events]
        sql = f"INSERT INTO {full_table} SELECT * FROM json.`/tmp/ocsf_batch`"

        ndjson_data = "\n".join(rows)

        async with httpx.AsyncClient(timeout=60) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            try:
                resp = await client.post(
                    f"{url}/api/2.0/sql/statements",
                    headers=headers,
                    json={
                        "statement": f"INSERT INTO {full_table} VALUES {self._to_sql_values(events[:1000])}",
                        "wait_timeout": "30s",
                        "on_wait_timeout": "CANCEL",
                    },
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    state = data.get("status", {}).get("state")
                    if state in ("SUCCEEDED", "RUNNING"):
                        return len(events), 0
                return 0, len(events)
            except Exception as e:
                return 0, len(events)

    def _to_sql_values(self, events: list[dict]) -> str:
        values = []
        for e in events[:10]:
            escaped = json.dumps(json.dumps(e)).strip('"')
            values.append(f"(parse_json('{escaped}'))")
        return ", ".join(values)
