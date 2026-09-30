from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    from app.models.connector import ConnectorModel  # noqa
    from app.models.forwarder import ForwarderModel  # noqa
    from app.models.mapping import MappingTemplateModel, PipelineRunModel  # noqa
    from app.models.user import UserModel  # noqa
    from app.models.approval import MappingApprovalModel, UnknownFieldModel, ApprovalDLQLinkModel  # noqa
    from app.models.settings import SettingModel  # noqa
    from app.models.audit_log import AuditLogModel  # noqa
    from app.models.dlq import DLQEventModel  # noqa
    from app.models.cron_job import CronJobModel  # noqa
    from app.models.anomaly import AnomalyModel, ConnectorBaselineModel, APIKeyModel  # noqa
    from app.models.doc_source import ConnectorDocSourceModel  # noqa
    from app.models.poll_state import ConnectorPollStateModel  # noqa
    from app.models.connector_ai import ConnectorAISettingsModel  # noqa
    from app.models.ingestion import IngestionStatModel, UnmappedFieldModel, PipelineCounterModel  # noqa
    from sqlalchemy.exc import OperationalError
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OperationalError as e:
        # Multiple uvicorn workers race to CREATE TABLE on startup — safe to ignore
        if "already exists" not in str(e):
            raise
