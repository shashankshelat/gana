"""
Monitors developer documentation pages for schema changes.
When a page changes, AI re-analyses the diff and creates a pending mapping approval.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime

import httpx

from app.core.database import AsyncSessionLocal
from app.models.doc_source import ConnectorDocSourceModel
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Official documentation pages for each connector type.
# These are checked periodically; any content change triggers AI re-analysis.
CONNECTOR_DOC_URLS: dict[str, list[dict]] = {
    "okta": [
        {
            "url": "https://developer.okta.com/docs/reference/api/system-log/",
            "description": "Okta System Log API - event schema and field reference",
        },
        {
            "url": "https://developer.okta.com/docs/reference/api/system-log/#attributes",
            "description": "Okta System Log event attributes",
        },
    ],
    "crowdstrike": [
        {
            "url": "https://falcon.crowdstrike.com/documentation/page/a2a7fc0e/streaming-api-event-dictionary",
            "description": "CrowdStrike Falcon Streaming API event dictionary",
        },
    ],
    "microsoft_defender": [
        {
            "url": "https://learn.microsoft.com/en-us/microsoft-365/security/defender-endpoint/advanced-hunting-schema-tables",
            "description": "Microsoft Defender for Endpoint advanced hunting schema",
        },
        {
            "url": "https://learn.microsoft.com/en-us/microsoft-365/security/defender/advanced-hunting-alertinfo-table",
            "description": "Defender AlertInfo table schema",
        },
    ],
    "microsoft_365": [
        {
            "url": "https://learn.microsoft.com/en-us/purview/audit-log-detailed-properties",
            "description": "Microsoft 365 Unified Audit Log detailed properties",
        },
        {
            "url": "https://learn.microsoft.com/en-us/office/office-365-management-api/office-365-management-activity-api-schema",
            "description": "Office 365 Management Activity API schema",
        },
    ],
    "zscaler": [
        {
            "url": "https://help.zscaler.com/zia/nss-feed-output-format-web-logs",
            "description": "Zscaler NSS feed output format for web logs",
        },
        {
            "url": "https://help.zscaler.com/zia/nss-feed-output-format-firewall-logs",
            "description": "Zscaler NSS feed output format for firewall logs",
        },
    ],
    "sentinelone": [
        {
            "url": "https://usea1-partners.sentinelone.net/docs/en/api-overview.html",
            "description": "SentinelOne API overview and threat event schema",
        },
    ],
    "palo_alto": [
        {
            "url": "https://docs.paloaltonetworks.com/pan-os/10-2/pan-os-admin/monitoring/use-syslog-for-monitoring/syslog-field-descriptions",
            "description": "PAN-OS syslog field descriptions",
        },
        {
            "url": "https://docs.paloaltonetworks.com/pan-os/10-2/pan-os-admin/monitoring/use-syslog-for-monitoring/syslog-field-descriptions/traffic-log-fields",
            "description": "PAN-OS traffic log fields",
        },
    ],
    "gcp_audit": [
        {
            "url": "https://cloud.google.com/logging/docs/reference/audit/auditlog/rest/Shared.Types/AuditLog",
            "description": "GCP AuditLog resource reference",
        },
        {
            "url": "https://cloud.google.com/logging/docs/audit/understanding-audit-logs",
            "description": "GCP Understanding Cloud Audit Logs",
        },
    ],
    "google_workspace": [
        {
            "url": "https://developers.google.com/workspace/admin/reports/v1/reference/activities/list",
            "description": "Google Workspace Admin SDK Reports API - activities",
        },
    ],
    "github": [
        {
            "url": "https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/reviewing-the-audit-log-for-your-organization",
            "description": "GitHub audit log event schema",
        },
        {
            "url": "https://docs.github.com/en/github-ae@latest/admin/monitoring-activity-in-your-enterprise/reviewing-audit-logs-for-your-enterprise/audit-log-events-for-your-enterprise",
            "description": "GitHub audit log events reference",
        },
    ],
    "cloudflare": [
        {
            "url": "https://developers.cloudflare.com/logs/reference/log-fields/zone/http_requests/",
            "description": "Cloudflare Logpush HTTP requests fields",
        },
        {
            "url": "https://developers.cloudflare.com/logs/reference/log-fields/zone/firewall_events/",
            "description": "Cloudflare firewall events log fields",
        },
    ],
    "duo_security": [
        {
            "url": "https://duo.com/docs/adminapi#authentication-logs",
            "description": "Duo Security Admin API authentication logs schema",
        },
        {
            "url": "https://duo.com/docs/adminapi#administrator-logs",
            "description": "Duo Security Admin API administrator logs schema",
        },
    ],
    "salesforce": [
        {
            "url": "https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_eventlogfile_login.htm",
            "description": "Salesforce Login EventLog file fields",
        },
        {
            "url": "https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_objects_eventlogfile.htm",
            "description": "Salesforce EventLogFile object reference",
        },
    ],
    "wiz": [
        {
            "url": "https://integrate.wiz.io/reference/issues",
            "description": "Wiz Issues API - finding/issue schema",
        },
    ],
    "slack": [
        {
            "url": "https://api.slack.com/admins/audit-logs",
            "description": "Slack Audit Logs API - event schema and action types",
        },
    ],
    "aws_cloudtrail": [
        {
            "url": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html",
            "description": "AWS CloudTrail event record contents",
        },
    ],
    "azure_ad": [
        {
            "url": "https://learn.microsoft.com/en-us/entra/identity/monitoring-health/reference-azure-monitor-sign-ins-log-schema",
            "description": "Microsoft Entra sign-in log schema",
        },
        {
            "url": "https://learn.microsoft.com/en-us/entra/identity/monitoring-health/reference-azure-monitor-audit-log-schema",
            "description": "Microsoft Entra audit log schema",
        },
    ],
}


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _fetch_page(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "GANA-DocWatcher/1.0"},
            )
            if resp.status_code == 200:
                return resp.text
            logger.warning("Doc fetch %s → HTTP %d", url, resp.status_code)
            return None
    except Exception as e:
        logger.warning("Doc fetch failed %s: %s", url, e)
        return None


async def _trigger_schema_update(connector_type: str, doc_url: str, new_content: str):
    """Create a pending AI approval when a doc page changes."""
    try:
        from app.api.settings import get_setting_value
        from app.core.ai_mapper import generate_mapping, AI_PROVIDERS

        provider = await get_setting_value("ai.default_provider", "claude")
        api_key = await get_setting_value(f"ai.{provider}_api_key", "")
        if not api_key:
            logger.info(
                "Doc changed for %s but no AI key configured — skipping auto re-analysis",
                connector_type,
            )
            return

        # Give AI the first 8 KB of the new doc page as sample context
        sample = new_content[:8000]
        model = AI_PROVIDERS[provider]["default_model"]
        result = await generate_mapping(
            sample_logs=f"# Developer documentation for {connector_type}\n\n{sample}",
            connector_type=connector_type,
            ocsf_class_uid=3002,
            provider=provider,
            model=model,
            api_key=api_key,
        )

        from app.models.approval import MappingApprovalModel
        async with AsyncSessionLocal() as db:
            approval = MappingApprovalModel(
                id=str(uuid.uuid4()),
                connector_type=connector_type,
                connector_name=connector_type,
                ocsf_class_uid=3002,
                source="doc_update",
                ai_provider=provider,
                ai_model=model,
                sample_logs=f"Doc change detected: {doc_url}",
                proposed_mapping=result["mapping"],
                current_mapping={},
                ai_explanation=(
                    f"Auto-generated after documentation change detected at {doc_url}.\n\n"
                    + result.get("explanation", "")
                ),
                status="pending",
                created_by="doc_watcher",
            )
            db.add(approval)
            await db.commit()
            logger.info(
                "Doc-update approval created for connector_type=%s approval=%s",
                connector_type, approval.id,
            )
    except Exception as e:
        logger.error("Schema update trigger failed for %s: %s", connector_type, e)


async def ensure_doc_sources():
    """Seed the DB with doc source entries for all known connectors (idempotent, multi-worker safe)."""
    import hashlib
    from app.models.doc_source import ConnectorDocSourceModel
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.exc import IntegrityError

    async with AsyncSessionLocal() as db:
        for connector_type, entries in CONNECTOR_DOC_URLS.items():
            for entry in entries:
                # Deterministic ID so concurrent workers produce the same primary key
                row_id = hashlib.md5(
                    f"{connector_type}:{entry['url']}".encode()
                ).hexdigest()
                stmt = (
                    sqlite_insert(ConnectorDocSourceModel)
                    .values(
                        id=row_id,
                        connector_type=connector_type,
                        url=entry["url"],
                        description=entry.get("description"),
                        enabled=True,
                        created_at=datetime.utcnow(),
                    )
                    .on_conflict_do_nothing()
                )
                try:
                    await db.execute(stmt)
                except IntegrityError:
                    await db.rollback()
        await db.commit()
    logger.info("Doc sources seeded for %d connector types", len(CONNECTOR_DOC_URLS))


async def run_doc_watcher():
    """
    Scheduled job: fetch all enabled doc pages, detect content changes,
    and trigger AI re-analysis for anything that changed.
    """
    logger.info("Doc watcher: starting check cycle")
    changed = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConnectorDocSourceModel).where(ConnectorDocSourceModel.enabled == True)
        )
        sources = result.scalars().all()

    for source in sources:
        content = await _fetch_page(source.url)
        if content is None:
            continue

        new_hash = _hash_content(content)
        now = datetime.utcnow()

        async with AsyncSessionLocal() as db:
            # Re-fetch within this session to update
            s = await db.get(ConnectorDocSourceModel, source.id)
            if s is None:
                continue

            s.last_checked_at = now

            if s.content_hash != new_hash:
                logger.info(
                    "Doc changed: connector=%s url=%s",
                    s.connector_type, s.url,
                )
                s.content_hash = new_hash
                s.last_changed_at = now
                changed += 1
                await db.commit()
                await _trigger_schema_update(s.connector_type, s.url, content)
            else:
                await db.commit()

    logger.info("Doc watcher: done — %d page(s) changed out of %d checked", changed, len(sources))
