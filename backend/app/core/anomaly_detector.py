import uuid
import logging
import math
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory sliding window: connector_id -> list of (timestamp, count) tuples
_windows: dict[str, list[tuple[float, int]]] = {}
WINDOW_SIZE = 30  # keep last 30 samples
MIN_SAMPLES = 10  # need at least this many to detect anomalies
SPIKE_Z_SCORE = 3.0
SILENCE_MINUTES = 15


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return mean, math.sqrt(variance)


def record_events(connector_id: str, count: int):
    import time
    window = _windows.setdefault(connector_id, [])
    window.append((time.time(), count))
    if len(window) > WINDOW_SIZE:
        _windows[connector_id] = window[-WINDOW_SIZE:]


async def check_for_anomalies(connector_id: str, connector_type: str, connector_name: str) -> list[dict]:
    window = _windows.get(connector_id, [])
    if len(window) < MIN_SAMPLES:
        return []

    counts = [c for _, c in window]
    mean, std = _mean_std(counts[:-1])
    latest = counts[-1]

    anomalies = []

    if std > 0:
        z_score = (latest - mean) / std
        if z_score > SPIKE_Z_SCORE:
            anomalies.append({
                "type": "volume_spike",
                "severity": "high" if z_score > 5 else "medium",
                "title": f"Volume spike on {connector_name}",
                "description": f"Events jumped to {latest} (baseline ~{mean:.0f}, z-score {z_score:.1f})",
                "baseline_value": mean,
                "observed_value": float(latest),
                "z_score": z_score,
            })
        elif z_score < -SPIKE_Z_SCORE and mean > 5:
            anomalies.append({
                "type": "volume_drop",
                "severity": "medium",
                "title": f"Volume drop on {connector_name}",
                "description": f"Events dropped to {latest} (baseline ~{mean:.0f}, z-score {z_score:.1f})",
                "baseline_value": mean,
                "observed_value": float(latest),
                "z_score": z_score,
            })

    if latest == 0 and mean > 5:
        import time
        last_ts = window[-1][0]
        silence_secs = time.time() - last_ts
        if silence_secs > SILENCE_MINUTES * 60:
            anomalies.append({
                "type": "silence",
                "severity": "high",
                "title": f"Connector silent: {connector_name}",
                "description": f"No events for {silence_secs / 60:.0f} minutes (expected ~{mean:.0f} per window)",
                "baseline_value": mean,
                "observed_value": 0.0,
                "z_score": None,
            })

    return anomalies


async def persist_anomalies(connector_id: str, connector_type: str, anomalies: list[dict]):
    if not anomalies:
        return
    from app.core.database import AsyncSessionLocal
    from app.models.anomaly import AnomalyModel
    from app.core.metrics import anomalies_detected

    async with AsyncSessionLocal() as db:
        for a in anomalies:
            model = AnomalyModel(
                id=str(uuid.uuid4()),
                connector_id=connector_id,
                connector_type=connector_type,
                anomaly_type=a["type"],
                severity=a["severity"],
                title=a["title"],
                description=a["description"],
                details=a,
                baseline_value=a.get("baseline_value"),
                observed_value=a.get("observed_value"),
                z_score=a.get("z_score"),
            )
            db.add(model)
            anomalies_detected.labels(anomaly_type=a["type"], severity=a["severity"]).inc()
        await db.commit()
