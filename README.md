# GANA — Map. Normalize. Understand.

> **High-throughput, source-available log normalization and forwarding platform built around the [Open Cybersecurity Schema Framework (OCSF)](https://schema.ocsf.io).**

Convert logs from any SaaS application or infrastructure source into OCSF-standard events, then route them to any SIEM or data lake — all configured through a web UI. The OCSF schema auto-updates from the official source so your mappings stay current as the standard evolves.

---

## Why This Exists

Every SIEM, data lake, and security tool ingests logs differently. Analysts spend enormous time writing and maintaining parsers instead of doing security work. OCSF is the industry's answer — a vendor-neutral, community-driven schema backed by AWS, Splunk, CrowdStrike, IBM, and 30+ others. This platform makes OCSF adoption operational: not just a schema you read about, but one your entire pipeline automatically normalizes to.

---

## Competitive Landscape

| Tool | OCSF Normalize | All SaaS Connectors | SIEM + Data Lake Forward | Auto-update Schema | Web UI | Kafka / High-throughput | Source / Licence |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **GANA (this)** | ✅ | ✅ 14 connectors | ✅ 7 destinations | ✅ runtime pull | ✅ | ✅ | ⚠️ source-available, free for noncommercial use |
| Cribl Stream | ✅ | ✅ 100+ packs | ✅ | ⚠️ manual redeploy | ✅ | ✅ | ❌ $0.60–1.50/GB |
| Tenzir | ✅ | ✅ 100+ | ✅ | ✅ | ✅ | ✅ | ⚠️ 500 GB/day cap |
| Datadog Pipelines | ✅ | ✅ via agent | ✅ | ⚠️ release-cycle | ✅ | ⚠️ | ❌ add-on cost |
| Monad (ex-Tarsal) | ⚠️ frozen v1.1.0 | ⚠️ partial | ⚠️ partial | ❌ | ✅ | ❌ | ❌ |
| Amazon Security Lake | ✅ AWS-only | ❌ needs pre-converted | ✅ subscriber | ✅ | ✅ | — | ❌ |
| Matano | ❌ uses ECS | ✅ 50+ | ⚠️ S3/Athena | — | ❌ | ✅ | ✅ |
| crowdalert/ocsf-vrl | ✅ | ❌ 5 sources | ❌ | ❌ | ❌ | ❌ | ✅ |

### Key differentiators

- **Auto-updating OCSF schema** — the only platform that pulls the latest schema from `schema.ocsf.io` at runtime. No manual redeployment, no frozen versions.
- **No per-GB pricing** — Cribl charges $0.60–$1.50/GB. GANA has no ingestion cost (free for noncommercial use; see [License](#license)).
- **Purpose-built for OCSF** — Cribl/Datadog treat OCSF as an output option. This platform is designed around OCSF from the ground up.
- **Visual mapping editor** — configure field mappings through a web UI, not YAML files.
- **14 pre-built SaaS connectors + 7 forwarder destinations in a single project**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Sources (Connectors)                     │
│  Okta · AWS CloudTrail · Azure AD · Google Workspace · Slack    │
│  GitHub · CrowdStrike · Cloudflare · Palo Alto · Salesforce     │
│  Microsoft Defender · Zscaler · Generic Webhook · Syslog        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ API polling / Webhooks / Streaming
                               ▼
                    ┌─────────────────────┐
                    │   Kafka Raw Topic    │  ← high-throughput
                    │  ocsf.raw.events    │     batch ingestion
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    OCSF Mapper       │  ← field normalization
                    │  (4 async workers)   │     severity/status/time
                    │  schema validation  │     dot-path rules
                    └──────────┬──────────┘
                               │
                    ┌─────────────────────┐
                    │  Kafka Mapped Topic  │
                    │  ocsf.mapped.events │
                    └──────────┬──────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        Forwarders (Destinations)                  │
│  Splunk HEC · Databricks · Elasticsearch · AWS S3                │
│  Azure Sentinel · Apache Kafka · Sumo Logic                      │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────┐
                    │   OCSF Schema Mgr    │  ← daily auto-pull
                    │  schema.ocsf.io     │     from GitHub releases
                    │  version tracking   │     + ocsf.io API
                    └─────────────────────┘
```

**Stack:** FastAPI · Apache Kafka · SQLite/PostgreSQL · Redis · React 18 · TypeScript · Tailwind CSS · Docker Compose

---

## Features

### Connectors (Sources)

| Connector | Auth | Method |
|-----------|------|--------|
| Okta | API Token | Poll + Webhook |
| AWS CloudTrail | IAM / Access Key | Poll (S3 or CloudWatch) |
| Azure Active Directory | OAuth2 | Poll |
| Google Workspace | Service Account | Poll |
| Salesforce | OAuth2 (Connected App) | Poll |
| Slack | Bot Token / Audit API | Poll + Webhook |
| GitHub | PAT / App Token | Poll + Webhook |
| CrowdStrike Falcon | OAuth2 | Poll + Streaming |
| Cloudflare | API Token | Poll + Webhook |
| Palo Alto NGFW / Cortex | API Key | Poll |
| Microsoft Defender for Endpoint | OAuth2 | Poll |
| Zscaler ZIA | API Key | Poll |
| Generic Webhook | HMAC Secret | Webhook |
| Generic Syslog | — | RFC3164 / RFC5424 / JSON |

### Forwarders (Destinations)

| Destination | Protocol | Batch Size |
|-------------|----------|------------|
| Splunk | HEC (HTTP Event Collector) | up to 500 |
| Databricks | REST API / Delta Lake | up to 10,000 |
| Elasticsearch / OpenSearch | Bulk API | up to 5,000 |
| AWS S3 | PutObject (gzip NDJSON) | up to 50,000 |
| Microsoft Sentinel | Log Analytics Data Collector API | up to 5,000 |
| Apache Kafka | Kafka Producer | up to 10,000 |
| Sumo Logic | HTTP Source | up to 1,000 |

### OCSF Schema Auto-Update

- On startup: checks GitHub releases for the latest schema version
- Daily scheduler: polls `schema.ocsf.io` and `api.github.com/repos/ocsf/ocsf-schema/releases/latest`
- Version comparison with semantic versioning
- Force-update endpoint: `POST /api/schema/update?force=true`
- All 6 OCSF categories and their event classes are browsable in the UI

### AI-Assisted Mapping

Paste 3–20 real log lines into the web UI, pick an AI provider, and get a complete OCSF field mapping back in seconds.

| Provider | Models |
|----------|--------|
| Anthropic Claude | claude-sonnet-4-6, claude-opus-4-8, claude-haiku-4-5-20251001 |
| OpenAI ChatGPT | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| Google Gemini | gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash |

The AI analyzes field names, types, and sample values, then:
1. Generates a `{ "ocsf.field": "source.field" }` mapping
2. Flags any source fields that **don't exist in the current OCSF schema** — these become **Unknown Field proposals**
3. Explains its mapping decisions in plain English

**Every AI-generated mapping goes into a pending approval queue — it does not go live until an admin or reviewer approves it.**

### Approval Workflow

```
AI Analysis → pending → reviewed by admin/reviewer → approved → mapping applied to connector
                                                   ↘ rejected → discarded
```

- Reviewers can **edit** the proposed mapping before approving
- Approval history is retained with reviewer name, timestamp, and note
- Role-based: `admin` and `reviewer` can approve; `viewer` can only read

### Unknown Field Proposals to OCSF

When AI finds a source field with no OCSF equivalent, it creates an **Unknown Field** record. From the Approvals page, admins can:
- Review the AI's description and suggested OCSF path
- Click **Submit to OCSF** — this opens a real GitHub issue on `ocsf/ocsf-schema` with a pre-filled field proposal
- Or **Ignore** the field if it's vendor-noise

### User Authentication

All routes require a JWT login. Three roles:

| Role | Can do |
|------|--------|
| `admin` | Everything — approve/reject, manage users, all writes |
| `reviewer` | Approve/reject mappings, submit OCSF field proposals |
| `viewer` | Read-only access to all pages |

Default credentials on first start: **`admin` / `admin123`** — change immediately in production.

### High-Throughput Design

- Apache Kafka with gzip compression, `acks=all`, idempotent producer
- 500-event batches with 100ms linger for producer-side coalescing
- 4 parallel async consumer workers per deployment
- Batch Kafka consumption (`getmany`) to minimize round-trips
- Async FastAPI with `uvicorn --workers 4`
- Redis for caching and rate-limiting

### Web UI

- **Dashboard** — live throughput chart (AreaChart), stats, pipeline health
- **Connectors** — card grid, enable/disable toggle, test connection, poll on-demand, webhook URL copy
- **Forwarders** — same pattern with severity filter rules
- **OCSF Schema** — browsable class tree by category, version info, manual update trigger
- **Pipeline Monitor** — live WebSocket throughput stream, architecture diagram
- **Light / Dark theme** — persisted in localStorage
- **Collapsible sidebar**

---

## Quick Start

### Docker (recommended)

```bash
git clone <repo-url> gana
cd gana
cp .env.example .env
docker compose up -d
```

Open [http://localhost:3000](http://localhost:3000)

> Kafka takes ~20 seconds to become healthy on first start. The backend retries automatically.

### Local Development

**Backend (requires Python 3.10+):**

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

DATABASE_URL="sqlite+aiosqlite:////tmp/ocsf.db" \
OCSF_SCHEMA_DIR="/tmp/ocsf_schema" \
KAFKA_BOOTSTRAP_SERVERS="localhost:9092" \
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173
```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
SECRET_KEY=your-random-secret

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_BATCH_SIZE=500
KAFKA_BATCH_TIMEOUT_MS=100

# OCSF schema auto-update interval (hours)
OCSF_SCHEMA_UPDATE_INTERVAL_HOURS=24

# Performance
MAX_WORKERS=4
PIPELINE_BATCH_SIZE=1000

# Switch to PostgreSQL for production
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ocsf
```

---

## OCSF Field Mapping

Each connector ships with default OCSF field mappings. You can override them in the UI or via the API.

**Dot-notation paths:**
```json
{
  "time": "published",
  "actor.user.name": "actor.displayName",
  "actor.user.email_addr": "actor.login",
  "src_endpoint.ip": "client.ipAddress",
  "severity_id": "$const:1"
}
```

- `"path.to.field"` — extracts a nested value from the raw event
- `"$const:value"` — sets a static value
- `{ "path": "field", "transform": "lower" }` — applies a transform (`lower`, `upper`, `int`, `str`, `epoch_ms`)

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/connectors/types` | List all available connector types |
| `GET` | `/api/connectors` | List configured connectors |
| `POST` | `/api/connectors` | Create a connector |
| `PATCH` | `/api/connectors/{id}` | Update a connector |
| `POST` | `/api/connectors/{id}/test` | Test connectivity |
| `POST` | `/api/connectors/{id}/poll` | Trigger manual poll |
| `POST` | `/api/connectors/webhooks/{type}/{id}` | Receive webhook events |
| `GET` | `/api/forwarders/types` | List all forwarder types |
| `GET` | `/api/forwarders` | List configured forwarders |
| `POST` | `/api/forwarders` | Create a forwarder |
| `POST` | `/api/forwarders/{id}/test` | Test forwarder connection |
| `GET` | `/api/schema/version` | Current OCSF schema version |
| `GET` | `/api/schema/classes` | All OCSF event classes |
| `POST` | `/api/schema/update` | Trigger schema update |
| `POST` | `/api/schema/validate` | Validate an event against OCSF |
| `GET` | `/api/pipeline/stats` | Pipeline throughput stats |
| `WS` | `/api/pipeline/stream` | Live stats WebSocket |
| `POST` | `/api/auth/login` | Login (returns JWT) |
| `GET` | `/api/auth/me` | Current user info |
| `GET` | `/api/auth/users` | List users (admin only) |
| `POST` | `/api/auth/users` | Create user (admin only) |
| `POST` | `/api/auth/change-password` | Change own password |
| `GET` | `/api/ai/providers` | List available AI providers and models |
| `POST` | `/api/ai/analyze` | Analyze sample logs and generate OCSF mapping |
| `GET` | `/api/approvals` | List mapping approvals |
| `GET` | `/api/approvals/{id}` | Get approval detail + unknown fields |
| `POST` | `/api/approvals/{id}/review` | Approve or reject a mapping |
| `GET` | `/api/approvals/unknown-fields/list` | List unknown OCSF fields |
| `POST` | `/api/approvals/unknown-fields/{id}/submit` | Submit field proposal to OCSF GitHub |
| `POST` | `/api/approvals/unknown-fields/{id}/ignore` | Ignore an unknown field |
| `GET` | `/health` | Health check |

Full interactive docs: `http://localhost:8000/docs`

---

## Adding a Custom Connector

Create `backend/app/connectors/my_source.py`:

```python
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector

@register_connector
class MySourceConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="my_source",
        display_name="My Source",
        description="Ingest events from My Source",
        icon="plug",
        category="cloud",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "api_key": {"type": "string", "title": "API Key", "secret": True},
            },
            "required": ["api_key"],
        },
        default_mapping={
            "time": "timestamp",
            "actor.user.name": "user.name",
        },
    )

    async def validate_config(self):
        return (True, "") if self.config.get("api_key") else (False, "api_key required")

    async def test_connection(self):
        return True, "OK"

    async def fetch_events(self, since=None):
        # Call your API here and return a list of raw event dicts
        return []
```

Then register it in `app/connectors/registry.py` → `load_all_connectors()`.

---

## Adding a Custom Forwarder

Create `backend/app/forwarders/my_dest.py`:

```python
from app.forwarders.base import BaseForwarder, ForwarderMeta
from app.forwarders.registry import register_forwarder

@register_forwarder
class MyDestForwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="my_dest",
        display_name="My Destination",
        description="Forward OCSF events to My Destination",
        icon="upload",
        category="siem",
        max_batch_size=1000,
        config_schema={
            "properties": {
                "url": {"type": "string", "title": "Endpoint URL"},
                "token": {"type": "string", "title": "Auth Token", "secret": True},
            },
            "required": ["url"],
        },
    )

    async def validate_config(self):
        return (True, "") if self.config.get("url") else (False, "url required")

    async def test_connection(self):
        return True, "OK"

    async def forward(self, events):
        # POST events to your destination
        # Return (success_count, failed_count)
        return len(events), 0
```

---

## Project Structure

```
gana/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                  # FastAPI app, lifespan, scheduler
│       ├── core/
│       │   ├── config.py            # Pydantic settings
│       │   ├── database.py          # SQLAlchemy async setup
│       │   ├── kafka_client.py      # Async producer/consumer
│       │   └── schema_manager.py   # OCSF schema auto-update
│       ├── connectors/             # 14 source connectors
│       ├── processors/
│       │   ├── mapper.py           # OCSF field normalization
│       │   └── pipeline.py         # Kafka consumer workers
│       ├── forwarders/             # 7 destination forwarders
│       ├── api/                    # FastAPI routes
│       └── models/                 # SQLAlchemy models
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── pages/                  # Dashboard, Connectors, Forwarders, Schema, Pipeline
        ├── components/             # Cards, Forms, Mapping editor, Layout
        ├── api/client.ts          # Axios API client
        ├── store/index.ts         # Zustand state (theme, sidebar)
        └── types/index.ts         # TypeScript types
```

---

## Roadmap

- [ ] PostgreSQL support for production deployments
- [ ] Role-based access control (RBAC)
- [ ] Connector scheduling (cron-based polling)
- [ ] Dead-letter queue with retry UI
- [ ] Alerting on pipeline failures (PagerDuty / Slack / email)
- [ ] More connectors: Microsoft 365, Jamf, Duo, Datadog, Wiz, Snyk, Lacework
- [ ] More forwarders: Chronicle (Google SecOps), Snowflake, Azure Event Hub, IBM QRadar
- [ ] OCSF event class auto-detection from raw log structure
- [ ] Prometheus metrics endpoint
- [ ] Helm chart for Kubernetes deployment

---

## Contributing

Contributions are welcome. The easiest way to contribute is adding a new connector or forwarder — the pluggable decorator pattern makes this straightforward (see examples above).

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-connector`
3. Add your connector/forwarder following the patterns in `app/connectors/` or `app/forwarders/`
4. Open a pull request

---

## OWASP Adoption

This project is a candidate for an official **OWASP Tool Project**. Below is the exact process.

> **Licence prerequisite:** OWASP projects must use an OSI-approved open-source licence (OWASP prefers Apache 2.0). GANA is currently released under the **PolyForm Noncommercial 1.0.0** licence, which is source-available, not open source. Applying to OWASP would require relicensing first. The text below assumes that has happened.

### Why OWASP is a good fit

- GANA solves a **security operations problem** (log visibility, normalization) — aligned with OWASP's mission
- It is the **only platform of its kind** that auto-updates the OCSF schema at runtime
- Would need relicensing to Apache 2.0 (OWASP's preferred license) — see the note above
- No commercial conflict — genuinely free, not a freemium product

### The four project tiers

OWASP uses a four-level maturity ladder (updated October 2022):

| Level | Meaning | How to reach it |
|-------|---------|----------------|
| **Incubator** | New project, proving value | Submit via Jira portal; approved by Project Committee |
| **Lab** | Usable deliverable published | Pass a deliverable review; at least 1 release submitted |
| **Production** | Stable, high-quality, actively maintained | Sustained releases (min 1/year); reviewed by Project Committee |
| **Flagship** | Exceptional strategic value to OWASP | Not applied for — Project Committee nominates; Board of Directors votes |

> Note: Flagship is a bonus designation, not the next step after Production. Most strong projects reach **Lab** or **Production** — that is a meaningful, respected endorsement.

### Step-by-step submission

**Step 1 — Read the policies first**
- Project Policy: https://owasp.org/www-policy/operational/projects
- Project Handbook: https://www.owasp.community/project-handbook

**Step 2 — Create a free OWASP account**
- Sign up at https://owasp.org (free; paid membership at $50/year gives extra benefits but is not required to submit)

**Step 3 — Submit via the OWASP Jira Service Desk**
- Portal: https://owasporg.atlassian.net/servicedesk/customer/portals
- File a **New Project Request** ticket. You will need:
  - Project name and one-line description
  - Project type: `Tool`
  - License: Apache 2.0 (after relicensing)
  - Your name as Project Leader
  - Link to this GitHub repository
  - How it helps the security community

**Step 4 — OWASP staff provision the project (~4–8 weeks)**
Once approved, OWASP staff automatically:
- Create `owasp.org/www-project-gana`
- Create the repo under `github.com/OWASP/www-project-gana`
- Issue an `@owasp.org` email to each project leader

**Step 5 — Build the project page (within 30 days)**
The project leader must publish the `owasp.org` project page within 30 days of receiving GitHub access.

### Who reviews applications

The **OWASP Project Committee** (meets monthly):
- **Chair:** Björn Kimminich (creator of OWASP Juice Shop)
- **Vice Chair:** Jeff Foley
- **Members:** Jason Gillam, Michael Bargury, Jim Manico
- Committee page: https://owasp.org/www-committee-project/

### Ongoing obligations as Project Leader

| Obligation | Requirement |
|-----------|------------|
| Activity | Minimum 1 release per year to stay "active" |
| Annual confirmation | Respond within 30 days when OWASP checks in |
| Email | Use `@owasp.org` email; respond within 9 business days |
| Leadership count | Maintain 2–5 co-leaders (personal role, not tied to employer) |
| Code of Conduct | Abide by https://owasp.org/www-policy/operational/code-of-conduct |
| Financials | All funds through the Foundation — no independent bank accounts |

### Suggested pitch for the application

> *"GANA is an open-source platform that normalizes security logs from 14 major SaaS sources (Okta, AWS CloudTrail, CrowdStrike, Azure AD, Salesforce, Slack, GitHub, etc.) into the OCSF standard and forwards them to any SIEM or data lake. It is the only open-source project that auto-updates OCSF schema definitions at runtime, eliminating the manual maintenance burden that prevents small security teams from adopting OCSF. Commercial alternatives (Cribl Stream at $0.60–$1.50/GB, Datadog Pipelines) are prohibitively expensive for most organizations. No open-source equivalent with comparable scope exists."*

### Recent precedents

| Project | Path | Timeline |
|---------|------|----------|
| OWASP GenAI Security Project | Incubator (May 2023) → **Flagship** (March 2025) | ~18 months — fastest known Flagship path |
| OWASP dep-scan | Donated by AppThreat → **Incubator** (Aug 2023) | Existing OSS tool donated and onboarded |
| OWASP Coraza WAF | Incubator → Lab → **Production** | Golang WAF, reached Production level |

### Useful links

| Resource | URL |
|----------|-----|
| Submit application | https://owasporg.atlassian.net/servicedesk/customer/portals |
| Project Policy | https://owasp.org/www-policy/operational/projects |
| Project Handbook | https://www.owasp.community/project-handbook |
| Project Committee | https://owasp.org/www-committee-project/ |
| All OWASP projects | https://owasp.org/projects/ |
| OWASP Slack (`#project-leaders`) | https://owasp.slack.com |

---

## License

Copyright (c) 2026 Shashank Shelat.

GANA is **source-available** under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may read, run and modify it for **noncommercial purposes**: personal use, research, education, hobby projects, and use by charities, schools and government bodies.

**Commercial use is not permitted** under this licence. That includes using GANA inside a company, offering it as a service, or selling or bundling it. For a commercial licence, contact the author via [LinkedIn](https://www.linkedin.com/in/shashankshelat).

---

## Acknowledgements

- [OCSF Schema](https://schema.ocsf.io) — the open standard this platform is built around
- [OCSF GitHub](https://github.com/ocsf/ocsf-schema) — schema definitions and releases
- [Amazon Security Lake](https://aws.amazon.com/security-lake/) — for driving OCSF industry adoption
- Inspired by the gap left by Cribl (expensive), Tenzir (capped free tier), and the absence of a purpose-built open-source OCSF pipeline

---

*Built to make OCSF adoption operational, not aspirational.*
