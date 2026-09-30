from typing import Type
from app.forwarders.base import BaseForwarder, ForwarderMeta


_registry: dict[str, Type[BaseForwarder]] = {}


def register_forwarder(cls: Type[BaseForwarder]) -> Type[BaseForwarder]:
    _registry[cls.meta.type_id] = cls
    return cls


def get_forwarder_class(type_id: str) -> Type[BaseForwarder] | None:
    return _registry.get(type_id)


def list_forwarder_types() -> list[dict]:
    result = []
    for type_id, cls in _registry.items():
        m: ForwarderMeta = cls.meta
        result.append({
            "type_id": m.type_id,
            "display_name": m.display_name,
            "description": m.description,
            "icon": m.icon,
            "category": m.category,
            "config_schema": m.config_schema,
            "supports_batch": m.supports_batch,
            "max_batch_size": m.max_batch_size,
            "maturity": m.maturity,
            "maturity_note": m.maturity_note,
        })
    return result


def instantiate_forwarder(type_id: str, forwarder_id: str, config: dict) -> BaseForwarder | None:
    cls = get_forwarder_class(type_id)
    if cls is None:
        return None
    return cls(forwarder_id=forwarder_id, config=config)


def load_all_forwarders():
    import app.forwarders.splunk  # noqa
    import app.forwarders.databricks  # noqa
    import app.forwarders.elasticsearch  # noqa
    import app.forwarders.s3  # noqa
    import app.forwarders.azure_sentinel  # noqa
    import app.forwarders.kafka_forwarder  # noqa
    import app.forwarders.chronicle  # noqa
    import app.forwarders.snowflake  # noqa
    import app.forwarders.bigquery  # noqa
    import app.forwarders.observability  # noqa
    import app.forwarders.cloud_logging  # noqa
    import app.forwarders.siem_http  # noqa
    import app.forwarders.syslog  # noqa
