from datetime import datetime
from sqlalchemy import String, Boolean, JSON, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ConnectorModel(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    mapping_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    ocsf_class_uid: Mapped[int] = mapped_column(Integer, nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String(255), nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    events_processed: Mapped[int] = mapped_column(Integer, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
