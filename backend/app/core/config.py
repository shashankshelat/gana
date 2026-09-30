from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    app_name: str = "GANA"
    app_version: str = "1.0.0"
    debug: bool = False

    secret_key: str = "changeme-in-production"

    database_url: str = "sqlite+aiosqlite:////data/ocsf.db"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_raw: str = "ocsf.raw.events"
    kafka_topic_mapped: str = "ocsf.mapped.events"
    kafka_topic_failed: str = "ocsf.failed.events"
    kafka_consumer_group: str = "ocsf-pipeline"
    kafka_batch_size: int = 500
    kafka_batch_timeout_ms: int = 100

    redis_url: str = "redis://localhost:6379"
    redis_ttl_seconds: int = 3600
    poll_interval_seconds: int = 60
    # How far back the first poll of a new connector reaches
    poll_initial_lookback_minutes: int = 60

    ocsf_schema_dir: str = "/data/ocsf_schema"
    ocsf_schema_update_interval_hours: int = 24
    ocsf_github_api: str = "https://api.github.com/repos/ocsf/ocsf-schema/releases/latest"
    ocsf_schema_api: str = "https://schema.ocsf.io/api/schema"

    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    max_workers: int = 4
    pipeline_batch_size: int = 1000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
