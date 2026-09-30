import json
from app.forwarders.base import BaseForwarder, ForwarderMeta, review_fields
from app.forwarders.registry import register_forwarder


@register_forwarder
class KafkaForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="kafka",
        display_name="Apache Kafka",
        description="Forward OCSF events to a downstream Kafka cluster or topic",
        icon="kafka",
        category="streaming",
        max_batch_size=10000,
        config_schema={
            "properties": {
                "bootstrap_servers": {"type": "string", "title": "Bootstrap Servers", "placeholder": "kafka1:9092,kafka2:9092"},
                "topic": {"type": "string", "title": "Target Topic", "default": "ocsf.events"},
                **review_fields("review_topic", "Review topic for unclassified events (blank = same topic)", "ocsf.events.review"),
                "security_protocol": {
                    "type": "string",
                    "title": "Security Protocol",
                    "enum": ["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"],
                    "default": "PLAINTEXT",
                },
                "sasl_mechanism": {"type": "string", "title": "SASL Mechanism", "enum": ["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"]},
                "sasl_username": {"type": "string", "title": "SASL Username"},
                "sasl_password": {"type": "string", "title": "SASL Password", "secret": True},
                "compression": {
                    "type": "string",
                    "title": "Compression",
                    "enum": ["none", "gzip", "snappy", "lz4", "zstd"],
                    "default": "gzip",
                },
                "partition_by_class": {"type": "boolean", "title": "Partition by Class UID", "default": False},
            },
            "required": ["bootstrap_servers", "topic"],
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        for field in ["bootstrap_servers", "topic"]:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            from aiokafka import AIOKafkaProducer
            producer = AIOKafkaProducer(
                bootstrap_servers=self.config["bootstrap_servers"],
            )
            await producer.start()
            await producer.stop()
            return True, "Kafka connection successful"
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        from aiokafka import AIOKafkaProducer
        import asyncio

        topic = self.config["topic"]
        compression = self.config.get("compression", "gzip")
        partition_by_class = self.config.get("partition_by_class", False)

        kwargs = {
            "bootstrap_servers": self.config["bootstrap_servers"],
            "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
            "compression_type": compression if compression != "none" else None,
        }

        protocol = self.config.get("security_protocol", "PLAINTEXT")
        if protocol in ("SASL_PLAINTEXT", "SASL_SSL"):
            kwargs["security_protocol"] = protocol
            kwargs["sasl_mechanism"] = self.config.get("sasl_mechanism", "PLAIN")
            kwargs["sasl_plain_username"] = self.config.get("sasl_username", "")
            kwargs["sasl_plain_password"] = self.config.get("sasl_password", "")

        producer = AIOKafkaProducer(**kwargs)
        await producer.start()
        success = 0
        failed = 0

        try:
            tasks = []
            for event in events:
                clean = {k: v for k, v in event.items() if not k.startswith("_")}
                key = str(event.get("class_uid", "")) if partition_by_class else None
                key_bytes = key.encode() if key else None
                target = self.config["review_topic"] if self.config.get("review_topic") and self.is_review(event) else topic
                tasks.append(producer.send(target, value=clean, key=key_bytes))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    failed += 1
                else:
                    success += 1
        finally:
            await producer.stop()

        return success, failed


@register_forwarder
class SumoLogicForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="sumo_logic",
        display_name="Sumo Logic",
        description="Forward OCSF events to Sumo Logic via HTTP Source endpoint",
        icon="sumo",
        category="siem",
        max_batch_size=1000,
        config_schema={
            "properties": {
                "http_source_url": {"type": "string", "title": "HTTP Source URL", "secret": True},
                "source_category": {"type": "string", "title": "Source Category", "default": "security/ocsf"},
                "source_host": {"type": "string", "title": "Source Host", "default": "gana"},
                "batch_size": {"type": "integer", "title": "Batch Size", "default": 100},
            },
            "required": ["http_source_url"],
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("http_source_url"):
            return False, "http_source_url is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            success, _ = await self.forward([{"_test": True, "class_uid": 3002}])
            return (True, "Connected") if success else (False, "Failed to send test event")
        except Exception as e:
            return False, str(e)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        import httpx
        url = self.config["http_source_url"]
        batch_size = self.config.get("batch_size", 100)
        headers = {
            "Content-Type": "application/json",
            "X-Sumo-Category": self.config.get("source_category", "security/ocsf"),
            "X-Sumo-Host": self.config.get("source_host", "gana"),
        }
        success = 0
        failed = 0
        clean_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]

        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(clean_events), batch_size):
                batch = clean_events[i:i + batch_size]
                payload = "\n".join(json.dumps(e) for e in batch)
                try:
                    resp = await client.post(url, content=payload.encode(), headers=headers)
                    if resp.status_code == 200:
                        success += len(batch)
                    else:
                        failed += len(batch)
                except Exception:
                    failed += len(batch)
        return success, failed
