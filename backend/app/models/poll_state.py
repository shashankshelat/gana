from datetime import datetime
from sqlalchemy import String, DateTime, Integer, BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ConnectorPollStateModel(Base):
    """Per-connector polling checkpoint so each poll only ingests events newer than the last one."""
    __tablename__ = "connector_poll_state"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checkpoint_ms: Mapped[int] = mapped_column(BigInteger, nullable=True)
    last_polled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), nullable=True)  # success | error | skipped
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_events: Mapped[int] = mapped_column(Integer, default=0)
