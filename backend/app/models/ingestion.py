from datetime import datetime
from sqlalchemy import String, DateTime, Integer, BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class IngestionStatModel(Base):
    """Daily event/byte totals per connector (raw logs received) and per forwarder (OCSF events delivered)."""
    __tablename__ = "ingestion_stats"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # "<day>|<kind>|<entity_id>"
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD (UTC)
    kind: Mapped[str] = mapped_column(String(20))  # connector | forwarder
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    events: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class UnmappedFieldModel(Base):
    """A raw field seen in a connector's logs that no mapping rule reads, with sample values."""
    __tablename__ = "unmapped_fields"

    id: Mapped[str] = mapped_column(String(600), primary_key=True)  # "<connector_id>|<field_path>"
    connector_id: Mapped[str] = mapped_column(String(36), index=True)
    connector_type: Mapped[str] = mapped_column(String(100))
    field_path: Mapped[str] = mapped_column(String(500))
    occurrences: Mapped[int] = mapped_column(BigInteger, default=0)
    sample_values: Mapped[list] = mapped_column(JSON, default=list)
    sample_event: Mapped[dict] = mapped_column(JSON, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PipelineCounterModel(Base):
    """Pipeline-wide counters, both all-time ("total" bucket) and per UTC minute for throughput/history charts."""
    __tablename__ = "pipeline_counters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "<bucket>|<name>"
    bucket: Mapped[str] = mapped_column(String(16), index=True)  # "total" or "YYYY-MM-DDTHH:MM"
    name: Mapped[str] = mapped_column(String(32))  # received | mapped | failed | forwarded | last_event_at
    value: Mapped[int] = mapped_column(BigInteger, default=0)
