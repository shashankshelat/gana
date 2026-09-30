from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=True)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success | failure
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Common action names
    # auth.login, auth.logout, auth.login_failed
    # connector.create, connector.update, connector.delete, connector.test, connector.poll
    # forwarder.create, forwarder.update, forwarder.delete, forwarder.test
    # approval.approved, approval.rejected
    # schema.updated, schema.force_updated
    # pii.settings_changed, ai.analyzed
    # user.created, user.updated, user.deactivated
