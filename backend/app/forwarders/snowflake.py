import json
import logging
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder

logger = logging.getLogger(__name__)


@register_forwarder
class SnowflakeForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="snowflake",
        display_name="Snowflake",
        description="Forward OCSF events to Snowflake via Snowflake Connector for Python",
        icon="snowflake",
        category="data_lake",
        max_batch_size=50000,
        config_schema={
            "properties": {
                "account": {"type": "string", "title": "Account Identifier", "placeholder": "org-account"},
                "user": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password", "secret": True},
                "private_key": {"type": "string", "title": "Private Key PEM (alternative to password)", "secret": True, "multiline": True},
                "warehouse": {"type": "string", "title": "Warehouse", "default": "COMPUTE_WH"},
                "database": {"type": "string", "title": "Database", "default": "SECURITY"},
                "schema": {"type": "string", "title": "Schema", "default": "OCSF"},
                "table": {"type": "string", "title": "Table", "default": "EVENTS"},
                "role": {"type": "string", "title": "Role", "default": "SYSADMIN"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 10000},
            },
            "required": ["account", "user", "database"],
        },
    )

    def _get_connection(self):
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError("snowflake-connector-python is required: pip install snowflake-connector-python")

        kwargs = {
            "account": self.config["account"],
            "user": self.config["user"],
            "warehouse": self.config.get("warehouse", "COMPUTE_WH"),
            "database": self.config["database"],
            "schema": self.config.get("schema", "OCSF"),
            "role": self.config.get("role", "SYSADMIN"),
        }
        if self.config.get("password"):
            kwargs["password"] = self.config["password"]
        elif self.config.get("private_key"):
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            pk = load_pem_private_key(self.config["private_key"].encode(), password=None)
            from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
            kwargs["private_key"] = pk.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        return snowflake.connector.connect(**kwargs)

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["account", "user", "database"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            conn = self._get_connection()
            conn.cursor().execute("SELECT CURRENT_VERSION()")
            conn.close()
            return True, "Connected to Snowflake"
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        import asyncio
        clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]

        def _sync_write():
            conn = self._get_connection()
            table = f"{self.config.get('schema', 'OCSF')}.{self.config.get('table', 'EVENTS')}"
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} (event VARIANT, inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP())")
            rows = [(json.dumps(e),) for e in clean]
            cursor.executemany(f"INSERT INTO {table} (event) SELECT PARSE_JSON(%s)", rows)
            conn.commit()
            conn.close()
            return len(events), 0

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_write)
        except Exception as e:
            logger.error("Snowflake forward failed: %s", e)
            return 0, len(events)
