from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ConnectorAISettingsModel(Base):
    """Per-connector AI mapping: automatic proposals from failed (DLQ) events, with cost guardrails."""
    __tablename__ = "connector_ai_settings"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_events: Mapped[int] = mapped_column(Integer, default=1)          # failed events needed before a run
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)   # minimum gap between automatic runs
    daily_limit: Mapped[int] = mapped_column(Integer, default=10)        # automatic runs per UTC day
    max_samples: Mapped[int] = mapped_column(Integer, default=10)        # failed events sent to the model per run
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(30), nullable=True)  # proposed | waiting_review | skipped | error
    last_message: Mapped[str] = mapped_column(Text, nullable=True)
    runs_day: Mapped[str] = mapped_column(String(10), nullable=True)
    runs_today: Mapped[int] = mapped_column(Integer, default=0)
