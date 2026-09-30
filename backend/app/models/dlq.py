from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DLQEventModel(Base):
    __tablename__ = "dlq_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(36), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=True)
    connector_name: Mapped[str] = mapped_column(String(255), nullable=True)
    raw_event: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    error_type: Mapped[str] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_retry_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
