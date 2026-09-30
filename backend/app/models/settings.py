from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SettingModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


DEFAULTS = {
    "app.name": ("GANA", False, "Application display name"),
    "app.default_ocsf_class_uid": ("3002", False, "Default OCSF class for new connectors"),
    "schema.update_interval_hours": ("24", False, "How often to check for OCSF schema updates"),
    "pii.enabled": ("false", False, "Enable PII detection and masking"),
    "pii.mode": ("mask", False, "Redaction mode: mask | hash | drop"),
    "pii.patterns": ('["email","credit_card","phone","ssn"]', False, "Active PII pattern types"),
    "alerts.slack_webhook": ("", True, "Slack webhook URL for pipeline alerts"),
    "alerts.pagerduty_key": ("", True, "PagerDuty integration key"),
    "alerts.connector_stale_minutes": ("30", False, "Minutes of silence before connector-down alert"),
    "ai.claude_api_key": ("", True, "Saved Anthropic API key"),
    "ai.openai_api_key": ("", True, "Saved OpenAI API key"),
    "ai.gemini_api_key": ("", True, "Saved Google Gemini API key"),
    "ai.default_provider": ("claude", False, "Default AI provider for mapping generation"),
    "cost.splunk_per_gb": ("0.80", False, "Splunk estimated cost per GB"),
    "cost.datadog_per_event": ("0.0000001", False, "Datadog estimated cost per event"),
    "sso.enabled": ("false", False, "Enable SSO/OIDC login"),
    "sso.provider_url": ("", False, "OIDC provider URL"),
    "sso.client_id": ("", False, "OIDC client ID"),
    "sso.client_secret": ("", True, "OIDC client secret"),
}
