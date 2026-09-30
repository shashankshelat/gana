import json
import httpx
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder


@register_forwarder
class ChronicleForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="chronicle",
        display_name="Google Chronicle (SecOps)",
        description="Forward OCSF events to Google Chronicle Security Operations via Ingestion API",
        icon="google",
        category="siem",
        max_batch_size=1000,
        config_schema={
            "properties": {
                "service_account_json": {"type": "string", "title": "Service Account JSON", "secret": True, "multiline": True},
                "region": {
                    "type": "string",
                    "title": "Region",
                    "enum": ["us", "eu", "asia-southeast1", "australia-southeast1"],
                    "default": "us",
                },
                "customer_id": {"type": "string", "title": "Customer ID (UUID)"},
                "log_type": {"type": "string", "title": "Log Type", "default": "OCSF"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 100},
            },
            "required": ["service_account_json", "customer_id"],
        },
    )

    async def _get_token(self) -> str:
        import json as json_lib
        import time
        try:
            import jwt as pyjwt
        except ImportError:
            raise ImportError("PyJWT required")
        sa_info = json_lib.loads(self.config["service_account_json"])
        now = int(time.time())
        claim = {
            "iss": sa_info["client_email"],
            "scope": "https://www.googleapis.com/auth/chronicle-backstory",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(claim, sa_info["private_key"], algorithm="RS256")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": token},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["service_account_json", "customer_id"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            await self._get_token()
            return True, "Chronicle token acquired"
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        token = await self._get_token()
        region = self.config.get("region", "us")
        customer_id = self.config["customer_id"]
        log_type = self.config.get("log_type", "OCSF")
        batch_size = self.config.get("batch_size", 100)

        base_url = f"https://{region}-backstory.googleapis.com"
        if region == "us":
            base_url = "https://malachiteingestion-pa.googleapis.com"

        success = 0
        failed = 0
        clean_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for i in range(0, len(clean_events), batch_size):
                batch = clean_events[i:i + batch_size]
                logs = [{"logText": json.dumps(e)} for e in batch]
                payload = {"customerId": customer_id, "logType": log_type, "entries": logs}
                try:
                    resp = await client.post(
                        f"{base_url}/v2/unstructuredlogentries:batchCreate",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code in (200, 201):
                        success += len(batch)
                    else:
                        failed += len(batch)
                except Exception:
                    failed += len(batch)

        return success, failed
