from datetime import datetime
from sqlalchemy import String, Boolean, JSON, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ForwarderModel(Base):
    __tablename__ = "forwarders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    forwarder_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    filter_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    batch_size: Mapped[int] = mapped_column(Integer, default=100)
    flush_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)
    events_forwarded: Mapped[int] = mapped_column(Integer, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, default=0)
    last_forwarded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
