import asyncio
import json
import logging
from typing import AsyncGenerator, Callable, Optional
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings

logger = logging.getLogger(__name__)

_producer: Optional[AIOKafkaProducer] = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type="gzip",
            max_batch_size=1048576,
            linger_ms=settings.kafka_batch_timeout_ms,
            acks="all",
            enable_idempotence=True,
        )
        await _producer.start()
    return _producer


async def close_producer():
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def produce_event(
    topic: str,
    value: dict,
    key: Optional[str] = None,
    partition: Optional[int] = None,
) -> None:
    producer = await get_producer()
    await producer.send_and_wait(topic, value=value, key=key, partition=partition)


async def produce_batch(topic: str, events: list[dict]) -> tuple[int, int]:
    producer = await get_producer()
    success = 0
    failed = 0
    tasks = []
    for event in events:
        key = event.get("metadata", {}).get("uid") or event.get("connector_id")
        tasks.append(producer.send(topic, value=event, key=str(key) if key else None))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            failed += 1
            logger.error("Kafka produce failed: %s", r)
        else:
            success += 1
    return success, failed


async def consume_events(
    topics: list[str],
    group_id: str,
    handler: Callable,
    batch_size: int = 100,
) -> None:
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=batch_size,
        fetch_max_wait_ms=500,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )
    await consumer.start()
    try:
        while True:
            batch = await consumer.getmany(timeout_ms=1000, max_records=batch_size)
            if not batch:
                continue
            events = []
            for tp, records in batch.items():
                for record in records:
                    events.append(record.value)
            if events:
                try:
                    await handler(events)
                    await consumer.commit()
                except Exception as e:
                    logger.error("Consumer handler failed: %s", e)
    finally:
        await consumer.stop()
