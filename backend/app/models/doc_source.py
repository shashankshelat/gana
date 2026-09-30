from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ConnectorDocSourceModel(Base):
    """
    Tracks developer documentation pages for each connector type.
    The doc watcher fetches these periodically; on content change it
    triggers AI to re-analyse the schema and creates a pending approval.
    """
    __tablename__ = "connector_doc_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("connector_type", "url", name="uq_doc_source_type_url"),)
