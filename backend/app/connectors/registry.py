from typing import Type
from app.connectors.base import BaseConnector, ConnectorMeta


_registry: dict[str, Type[BaseConnector]] = {}


def register_connector(cls: Type[BaseConnector]) -> Type[BaseConnector]:
    _registry[cls.meta.type_id] = cls
    return cls


def get_connector_class(type_id: str) -> Type[BaseConnector] | None:
    return _registry.get(type_id)


def list_connector_types() -> list[dict]:
    result = []
    for type_id, cls in _registry.items():
        m: ConnectorMeta = cls.meta
        result.append({
            "type_id": m.type_id,
            "display_name": m.display_name,
            "description": m.description,
            "icon": m.icon,
            "category": m.category,
            "auth_methods": m.auth_methods,
            "supports_webhook": m.supports_webhook,
            "supports_polling": m.supports_polling,
            "supports_streaming": m.supports_streaming,
            "default_ocsf_class_uid": m.default_ocsf_class_uid,
            "config_schema": m.config_schema,
            "default_mapping": m.default_mapping,
            "maturity": m.maturity,
            "maturity_note": m.maturity_note,
        })
    return result


def instantiate_connector(type_id: str, connector_id: str, config: dict, mapping_rules: dict) -> BaseConnector | None:
    cls = get_connector_class(type_id)
    if cls is None:
        return None
    return cls(connector_id=connector_id, config=config, mapping_rules=mapping_rules)


def load_all_connectors():
    import app.connectors.okta  # noqa
    import app.connectors.aws_cloudtrail  # noqa
    import app.connectors.azure_ad  # noqa
    import app.connectors.google_workspace  # noqa
    import app.connectors.salesforce  # noqa
    import app.connectors.slack  # noqa
    import app.connectors.github_connector  # noqa
    import app.connectors.crowdstrike  # noqa
    import app.connectors.cloudflare  # noqa
    import app.connectors.palo_alto  # noqa
    import app.connectors.microsoft_defender  # noqa
    import app.connectors.zscaler  # noqa
    import app.connectors.wiz  # noqa
    import app.connectors.duo_security  # noqa
    import app.connectors.microsoft_365  # noqa
    import app.connectors.sentinelone  # noqa
    import app.connectors.gcp_audit  # noqa
    import app.connectors.generic_webhook  # noqa
    import app.connectors.generic_syslog  # noqa
    import app.connectors.alert_platforms  # noqa
