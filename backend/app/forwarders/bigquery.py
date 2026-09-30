import json
import logging
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder

logger = logging.getLogger(__name__)


@register_forwarder
class BigQueryForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="bigquery",
        display_name="Google BigQuery",
        description="Forward OCSF events to Google BigQuery via Streaming Insert API",
        icon="google",
        category="data_lake",
        max_batch_size=10000,
        config_schema={
            "properties": {
                "service_account_json": {"type": "string", "title": "Service Account JSON", "secret": True, "multiline": True},
                "project_id": {"type": "string", "title": "GCP Project ID"},
                "dataset_id": {"type": "string", "title": "Dataset ID", "default": "ocsf"},
                "table_id": {"type": "string", "title": "Table ID", "default": "events"},
                "create_if_missing": {"type": "boolean", "title": "Create Table if Missing", "default": True},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 500},
            },
            "required": ["service_account_json", "project_id"],
        },
    )

    async def _get_token(self) -> str:
        import time
        try:
            import jwt as pyjwt
        except ImportError:
            raise ImportError("PyJWT required")
        sa_info = json.loads(self.config["service_account_json"])
        now = int(time.time())
        claim = {
            "iss": sa_info["client_email"],
            "scope": "https://www.googleapis.com/auth/bigquery.insertdata https://www.googleapis.com/auth/bigquery",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(claim, sa_info["private_key"], algorithm="RS256")
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": token},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["service_account_json", "project_id"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await self._get_token()
            return True, "BigQuery token acquired"
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        import httpx
        token = await self._get_token()
        project = self.config["project_id"]
        dataset = self.config.get("dataset_id", "ocsf")
        table = self.config.get("table_id", "events")
        batch_size = self.config.get("batch_size", 500)

        clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]
        success = 0
        failed = 0
        url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}/insertAll"

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for i in range(0, len(clean), batch_size):
                batch = clean[i:i + batch_size]
                payload = {"rows": [{"json": e} for e in batch]}
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        insert_errors = data.get("insertErrors", [])
                        failed_in_batch = len(insert_errors)
                        success += len(batch) - failed_in_batch
                        failed += failed_in_batch
                    else:
                        failed += len(batch)
                except Exception:
                    failed += len(batch)

        return success, failed
