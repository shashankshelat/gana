#!/usr/bin/env python3
"""GANA CLI (Map. Normalize. Understand.): interact with your pipeline from the terminal."""

import json
import sys
import os

import click
import httpx


def _get_base_url():
    return os.environ.get("GANA_URL") or os.environ.get("OCSF_PIPELINE_URL", "http://localhost:8000")


def _get_token():
    return os.environ.get("GANA_TOKEN") or os.environ.get("OCSF_PIPELINE_TOKEN", "")


def _headers():
    token = _get_token()
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _api(method: str, path: str, **kwargs):
    url = _get_base_url() + path
    try:
        resp = httpx.request(method, url, headers=_headers(), timeout=30, **kwargs)
        return resp
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to {_get_base_url()}. Is the pipeline running?", err=True)
        sys.exit(1)


@click.group()
@click.version_option("1.0.0", prog_name="gana")
def cli():
    """GANA — Map. Normalize. Understand. Open-source security log normalization to OCSF."""
    pass


# ── Auth ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--url", default="http://localhost:8000", help="Pipeline base URL")
@click.option("--username", prompt=True)
@click.option("--password", prompt=True, hide_input=True)
def login(url, username, password):
    """Login and save token to environment."""
    resp = httpx.post(f"{url}/api/auth/login", data={"username": username, "password": password}, timeout=10)
    if resp.status_code == 200:
        token = resp.json()["access_token"]
        click.echo(f"\nLogin successful! Set these environment variables:\n")
        click.echo(f"  export GANA_URL={url}")
        click.echo(f"  export GANA_TOKEN={token}\n")
    else:
        click.echo(f"Login failed: {resp.text}", err=True)
        sys.exit(1)


# ── Connectors ────────────────────────────────────────────────────────────────

@cli.group()
def connectors():
    """Manage connectors."""
    pass


@connectors.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_connectors(as_json):
    """List all configured connectors."""
    resp = _api("GET", "/api/connectors")
    data = resp.json()
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"\n{'NAME':<30} {'TYPE':<20} {'STATUS':<10} {'EVENTS':>10}\n" + "-" * 72)
        for c in data:
            status = "active" if c["enabled"] else "disabled"
            click.echo(f"{c['name']:<30} {c['connector_type']:<20} {status:<10} {c['events_processed']:>10,}")
        click.echo()


@connectors.command("test")
@click.argument("connector_id")
def test_connector(connector_id):
    """Test a connector's connection."""
    resp = _api("POST", f"/api/connectors/{connector_id}/test")
    data = resp.json()
    icon = "✓" if data.get("success") else "✗"
    click.echo(f"{icon} {data.get('message', 'Unknown')}")


@connectors.command("poll")
@click.argument("connector_id")
def poll_connector(connector_id):
    """Manually trigger a connector poll."""
    resp = _api("POST", f"/api/connectors/{connector_id}/poll")
    data = resp.json()
    click.echo(f"Received: {data.get('events_received', 0)}, Queued: {data.get('queued', 0)}, Failed: {data.get('failed', 0)}")


# ── AI Mapping ────────────────────────────────────────────────────────────────

@cli.command("analyze")
@click.option("--file", "-f", "log_file", type=click.Path(exists=True), help="Log file to analyze")
@click.option("--provider", default="claude", type=click.Choice(["claude", "openai", "gemini"]))
@click.option("--connector-type", default="generic_webhook", help="Connector type name")
@click.option("--class-uid", default=3002, type=int, help="OCSF class UID")
@click.option("--api-key", envvar="AI_API_KEY", help="AI provider API key")
def analyze(log_file, provider, connector_type, class_uid, api_key):
    """Analyze sample logs and generate OCSF mapping using AI."""
    if not api_key:
        click.echo("Error: --api-key or AI_API_KEY env var required", err=True)
        sys.exit(1)

    if log_file:
        with open(log_file) as f:
            sample_logs = f.read()
    else:
        click.echo("Paste sample logs (Ctrl+D when done):")
        sample_logs = sys.stdin.read()

    click.echo(f"\nAnalyzing with {provider}...")
    resp = _api("POST", "/api/ai/analyze", json={
        "sample_logs": sample_logs,
        "connector_type": connector_type,
        "ocsf_class_uid": class_uid,
        "provider": provider,
        "api_key": api_key,
    })

    data = resp.json()
    click.echo(f"\nApproval ID: {data.get('approval_id')}")
    click.echo(f"\nProposed Mapping:")
    click.echo(json.dumps(data.get("proposed_mapping", {}), indent=2))

    unknown = data.get("unknown_source_fields", [])
    if unknown:
        click.echo(f"\n{len(unknown)} fields not in OCSF schema:")
        for f in unknown:
            click.echo(f"  • {f.get('field_name')}: {f.get('description', '')[:80]}")

    click.echo(f"\nStatus: pending approval (review at {_get_base_url()}/approvals)")


# ── Schema ────────────────────────────────────────────────────────────────────

@cli.group()
def schema():
    """Manage OCSF schema."""
    pass


@schema.command("version")
def schema_version():
    """Show current OCSF schema version."""
    resp = _api("GET", "/api/schema/version")
    data = resp.json()
    click.echo(f"Version: {data.get('version', 'unknown')}")
    click.echo(f"Updated: {data.get('updated_at', 'unknown')}")


@schema.command("update")
@click.option("--force", is_flag=True, help="Force update even if already current")
def schema_update(force):
    """Trigger an OCSF schema update."""
    resp = _api("POST", f"/api/schema/update?force={str(force).lower()}")
    data = resp.json()
    click.echo(f"Status: {data.get('status')}, Version: {data.get('version', 'unknown')}")


@schema.command("validate")
@click.argument("event_file", type=click.Path(exists=True))
def schema_validate(event_file):
    """Validate an OCSF event JSON file."""
    with open(event_file) as f:
        event = json.load(f)
    resp = _api("POST", "/api/schema/validate", json=event)
    data = resp.json()
    if data.get("valid"):
        click.echo("✓ Event is valid OCSF")
    else:
        click.echo("✗ Validation errors:")
        for err in data.get("errors", []):
            click.echo(f"  • {err}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show pipeline status."""
    resp = _api("GET", "/api/stats/overview")
    data = resp.json()
    click.echo(f"\nGANA Status")
    click.echo(f"{'─' * 30}")
    click.echo(f"  Throughput:  {data.get('throughput_per_second', 0)} events/sec")
    click.echo(f"  Received:    {data.get('events_received', 0):,}")
    click.echo(f"  Mapped:      {data.get('events_mapped', 0):,}")
    click.echo(f"  Failed:      {data.get('events_failed', 0):,}")
    click.echo(f"  Connectors:  {data.get('enabled_connectors', 0)}/{data.get('total_connectors', 0)} active")
    click.echo(f"  Forwarders:  {data.get('total_forwarders', 0)} configured\n")


if __name__ == "__main__":
    cli()
