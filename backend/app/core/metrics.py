from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

registry = CollectorRegistry()

events_received = Counter(
    "ocsf_events_received_total",
    "Total raw events received",
    ["connector_type"],
    registry=registry,
)

events_mapped = Counter(
    "ocsf_events_mapped_total",
    "Total events successfully mapped to OCSF",
    ["class_uid", "connector_type"],
    registry=registry,
)

events_failed = Counter(
    "ocsf_events_failed_total",
    "Total events that failed mapping or forwarding",
    ["error_type", "connector_type"],
    registry=registry,
)

events_forwarded = Counter(
    "ocsf_events_forwarded_total",
    "Total events forwarded to destinations",
    ["forwarder_type"],
    registry=registry,
)

mapping_duration = Histogram(
    "ocsf_mapping_duration_seconds",
    "Time spent mapping a batch of events",
    ["connector_type"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    registry=registry,
)

forwarder_duration = Histogram(
    "ocsf_forwarder_duration_seconds",
    "Time spent forwarding a batch of events",
    ["forwarder_type"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0],
    registry=registry,
)

dlq_size = Gauge(
    "ocsf_dlq_size",
    "Current number of events in the dead-letter queue",
    registry=registry,
)

active_connectors = Gauge(
    "ocsf_active_connectors",
    "Number of enabled connectors",
    registry=registry,
)

anomalies_detected = Counter(
    "ocsf_anomalies_detected_total",
    "Total anomalies detected",
    ["anomaly_type", "severity"],
    registry=registry,
)

pii_fields_masked = Counter(
    "ocsf_pii_fields_masked_total",
    "Total PII field values masked",
    ["pattern_type"],
    registry=registry,
)


def get_metrics_output() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
