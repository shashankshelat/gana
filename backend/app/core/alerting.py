import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

_settings_cache: dict = {}


async def _get_setting(key: str, default: str = "") -> str:
    try:
        # Decrypts secret settings (webhook URLs, PagerDuty key)
        from app.api.settings import get_setting_value
        return await get_setting_value(key, default)
    except Exception:
        return default


async def send_alert(title: str, message: str, level: str = "warning", details: Optional[dict] = None):
    slack_url = await _get_setting("alerts.slack_webhook")
    pagerduty_key = await _get_setting("alerts.pagerduty_key")

    tasks = []
    if slack_url:
        tasks.append(_send_slack(slack_url, title, message, level))
    if pagerduty_key:
        tasks.append(_send_pagerduty(pagerduty_key, title, message, level))

    if not tasks:
        logger.warning("[ALERT][%s] %s — %s", level.upper(), title, message)
        return

    import asyncio
    await asyncio.gather(*tasks, return_exceptions=True)


async def _send_slack(webhook_url: str, title: str, message: str, level: str):
    colors = {"info": "#36a64f", "warning": "#ff9800", "error": "#f44336", "critical": "#9c27b0"}
    payload = {
        "attachments": [{
            "color": colors.get(level, "#888888"),
            "title": f"GANA — {title}",
            "text": message,
            "footer": "GANA · Map. Normalize. Understand.",
        }]
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(webhook_url, json=payload)
        except Exception as e:
            logger.error("Slack alert failed: %s", e)


async def _send_pagerduty(integration_key: str, title: str, message: str, level: str):
    severity_map = {"info": "info", "warning": "warning", "error": "error", "critical": "critical"}
    payload = {
        "routing_key": integration_key,
        "event_action": "trigger",
        "payload": {
            "summary": f"GANA: {title}",
            "severity": severity_map.get(level, "warning"),
            "source": "gana",
            "custom_details": {"message": message},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post("https://events.pagerduty.com/v2/enqueue", json=payload)
        except Exception as e:
            logger.error("PagerDuty alert failed: %s", e)


async def check_connector_health():
    from datetime import datetime, timedelta
    from app.core.database import AsyncSessionLocal
    from app.models.connector import ConnectorModel
    from sqlalchemy import select

    stale_minutes_str = await _get_setting("alerts.connector_stale_minutes", "30")
    try:
        stale_minutes = int(stale_minutes_str)
    except ValueError:
        stale_minutes = 30

    threshold = datetime.utcnow() - timedelta(minutes=stale_minutes)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConnectorModel).where(
                ConnectorModel.enabled == True,
                ConnectorModel.last_event_at < threshold,
            )
        )
        stale = result.scalars().all()

    for connector in stale:
        await send_alert(
            title=f"Connector Silent: {connector.name}",
            message=f"Connector '{connector.name}' ({connector.connector_type}) has not produced events in over {stale_minutes} minutes.",
            level="warning",
        )
