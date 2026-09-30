import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import init_db
from app.core.schema_manager import schema_manager
from app.connectors.registry import load_all_connectors
from app.forwarders.registry import load_all_forwarders
from app.api import connectors, forwarders, schema, pipeline, health
from app.api.auth import router as auth_router, ensure_default_admin
from app.api.ai_mapping import router as ai_router
from app.api.approvals import router as approvals_router
from app.api.settings import router as settings_router, ensure_defaults
from app.api.audit_log import router as audit_router
from app.api.dlq import router as dlq_router
from app.api.cron import router as cron_router, load_cron_jobs
from app.api.metrics import router as metrics_router
from app.api.anomaly import router as anomaly_router
from app.api.cost import router as cost_router
from app.core.doc_watcher import ensure_doc_sources, run_doc_watcher
from app.core.poller import run_scheduled_polls
from app.core.ai_autofix import run_automatic as run_ai_autofix
from app.core.ingestion_tracker import flush as flush_ingestion_stats
from app.api.doc_sources import router as doc_sources_router
from app.api.ingestion import router as ingestion_router
from app.api.connector_ai import router as connector_ai_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_pipeline_task = None
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GANA...")

    await init_db()
    await ensure_default_admin()
    await ensure_defaults()
    load_all_connectors()
    load_all_forwarders()

    from app.core.mapping_cache import mapping_cache
    await mapping_cache.load()

    await ensure_doc_sources()

    from app.core.ingestion_tracker import seed_counters_if_empty
    await seed_counters_if_empty()

    await schema_manager.update_schema(force=False)

    scheduler.add_job(
        schema_manager.update_schema,
        "interval",
        hours=settings.ocsf_schema_update_interval_hours,
        id="ocsf_schema_update",
    )
    scheduler.add_job(
        _run_connector_health_check,
        "interval",
        minutes=5,
        id="connector_health_check",
    )
    scheduler.add_job(
        run_scheduled_polls,
        "interval",
        seconds=settings.poll_interval_seconds,
        id="connector_polling",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_ai_autofix,
        "interval",
        minutes=5,
        id="ai_autofix",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        flush_ingestion_stats,
        "interval",
        seconds=10,
        id="ingestion_stats_flush",
        max_instances=1,
    )
    scheduler.add_job(
        run_doc_watcher,
        "interval",
        hours=24,
        id="doc_watcher",
    )
    scheduler.start()

    await load_cron_jobs(scheduler)

    try:
        from app.processors.pipeline import start_pipeline_workers
        global _pipeline_task
        _pipeline_task = asyncio.create_task(start_pipeline_workers())
        logger.info("Pipeline workers started")
    except Exception as e:
        logger.warning("Could not start pipeline workers (Kafka unavailable): %s", e)

    logger.info("GANA ready — v%s", settings.app_version)
    yield

    scheduler.shutdown(wait=False)
    await flush_ingestion_stats()
    if _pipeline_task:
        _pipeline_task.cancel()
        try:
            await _pipeline_task
        except asyncio.CancelledError:
            pass

    from app.core.kafka_client import close_producer
    await close_producer()
    logger.info("GANA stopped")


async def _run_connector_health_check():
    from app.core.alerting import check_connector_health
    try:
        await check_connector_health()
    except Exception as e:
        logger.error("Connector health check failed: %s", e)


app = FastAPI(
    title="GANA",
    description="GANA — Map. Normalize. Understand. Normalizes security logs to OCSF and routes them to any SIEM or data lake.",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_router)
app.include_router(connectors.router)
app.include_router(forwarders.router)
app.include_router(schema.router)
app.include_router(pipeline.router)
app.include_router(ai_router)
app.include_router(approvals_router)
app.include_router(settings_router)
app.include_router(audit_router)
app.include_router(dlq_router)
app.include_router(cron_router)
app.include_router(metrics_router)
app.include_router(anomaly_router)
app.include_router(cost_router)
app.include_router(doc_sources_router)
app.include_router(ingestion_router)
app.include_router(connector_ai_router)
