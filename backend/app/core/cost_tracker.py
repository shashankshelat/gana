import logging
from typing import Optional

logger = logging.getLogger(__name__)

COST_MODELS = {
    "splunk": {"unit": "per_gb", "default_rate": 0.80, "setting_key": "cost.splunk_per_gb"},
    "databricks": {"unit": "per_event", "default_rate": 0.0000005, "setting_key": "cost.databricks_per_event"},
    "elasticsearch": {"unit": "per_gb", "default_rate": 0.25, "setting_key": "cost.elasticsearch_per_gb"},
    "s3": {"unit": "per_gb", "default_rate": 0.023, "setting_key": "cost.s3_per_gb"},
    "datadog": {"unit": "per_event", "default_rate": 0.0000001, "setting_key": "cost.datadog_per_event"},
    "azure_sentinel": {"unit": "per_gb", "default_rate": 2.46, "setting_key": "cost.sentinel_per_gb"},
    "bigquery": {"unit": "per_gb", "default_rate": 0.01, "setting_key": "cost.bigquery_per_gb"},
    "snowflake": {"unit": "per_credit", "default_rate": 3.00, "setting_key": "cost.snowflake_per_credit"},
    "sumo_logic": {"unit": "per_gb", "default_rate": 1.50, "setting_key": "cost.sumologic_per_gb"},
    "chronicle": {"unit": "per_gb", "default_rate": 0.00, "setting_key": "cost.chronicle_per_gb"},
    "kafka": {"unit": "per_gb", "default_rate": 0.10, "setting_key": "cost.kafka_per_gb"},
}

AVG_EVENT_SIZE_BYTES = 2048  # ~2KB per OCSF event


async def estimate_monthly_cost(
    events_per_second: float,
    enabled_forwarder_types: list[str],
) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.models.settings import SettingModel
    from sqlalchemy import select

    monthly_events = events_per_second * 60 * 60 * 24 * 30
    monthly_gb = (monthly_events * AVG_EVENT_SIZE_BYTES) / (1024 ** 3)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SettingModel))
        settings_rows = result.scalars().all()
    settings = {r.key: r.value for r in settings_rows}

    breakdown = []
    total = 0.0

    for ftype in enabled_forwarder_types:
        model = COST_MODELS.get(ftype)
        if not model:
            continue
        rate_str = settings.get(model["setting_key"], str(model["default_rate"]))
        try:
            rate = float(rate_str)
        except ValueError:
            rate = model["default_rate"]

        if model["unit"] == "per_gb":
            cost = monthly_gb * rate
        elif model["unit"] == "per_event":
            cost = monthly_events * rate
        else:
            cost = 0.0

        breakdown.append({
            "forwarder_type": ftype,
            "unit": model["unit"],
            "rate": rate,
            "estimated_monthly_usd": round(cost, 2),
        })
        total += cost

    return {
        "events_per_second": events_per_second,
        "monthly_events_estimate": int(monthly_events),
        "monthly_gb_estimate": round(monthly_gb, 3),
        "total_estimated_monthly_usd": round(total, 2),
        "breakdown": breakdown,
    }
