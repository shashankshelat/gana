from datetime import datetime
from sqlalchemy import String, JSON, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MappingApprovalModel(Base):
    __tablename__ = "mapping_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(36), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=True)
    connector_name: Mapped[str] = mapped_column(String(255), nullable=True)
    ocsf_class_uid: Mapped[int] = mapped_column(Integer, nullable=True)

    source: Mapped[str] = mapped_column(String(50), default="ai")  # "ai" or "manual"
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=True)

    sample_logs: Mapped[str] = mapped_column(Text, nullable=True)
    proposed_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    current_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, approved, rejected
    reviewed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    reviewer_note: Mapped[str] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UnknownFieldModel(Base):
    __tablename__ = "unknown_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(36), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_path: Mapped[str] = mapped_column(String(500), nullable=True)
    sample_values: Mapped[dict] = mapped_column(JSON, default=list)
    ai_description: Mapped[str] = mapped_column(Text, nullable=True)
    ai_suggested_ocsf_path: Mapped[str] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, submitted, ignored
    github_issue_url: Mapped[str] = mapped_column(String(500), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalDLQLinkModel(Base):
    """DLQ events an AI mapping fix was generated from, so approving the fix can retry them."""
    __tablename__ = "approval_dlq_links"

    approval_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dlq_event_ids: Mapped[list] = mapped_column(JSON, default=list)
