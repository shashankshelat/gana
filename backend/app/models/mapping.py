from datetime import datetime
from sqlalchemy import String, JSON, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MappingTemplateModel(Base):
    __tablename__ = "mapping_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    ocsf_class_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    ocsf_class_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapping_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineRunModel(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(36), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    events_received: Mapped[int] = mapped_column(Integer, default=0)
    events_mapped: Mapped[int] = mapped_column(Integer, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, default=0)
    events_forwarded: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    error_summary: Mapped[dict] = mapped_column(JSON, default=dict)
