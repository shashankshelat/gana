from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AnomalyModel(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(36), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=True)
    anomaly_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Types: volume_spike, volume_drop, silence, severity_spike, new_field, error_rate_spike
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | critical
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=True)
    observed_value: Mapped[float] = mapped_column(Float, nullable=True)
    z_score: Mapped[float] = mapped_column(Float, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Integer, default=0)
    acknowledged_by: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectorBaselineModel(Base):
    __tablename__ = "connector_baselines"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    window_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    # { "mean": float, "std": float, "samples": [int, ...], "last_updated": str }
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
