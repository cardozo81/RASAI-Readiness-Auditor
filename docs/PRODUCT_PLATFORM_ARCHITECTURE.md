# RASAi Product Platform Architecture

Status: implemented product-platform architecture with SQLite local/default persistence and an explicit PostgreSQL 18 control-plane backend under cross-platform regression validation.

## Objective

RASAi is structured as a product platform supporting multi-user, multi-client, multi-project and multi-domain operation while preserving immutable audit evidence as a separate concern.

The architectural rule is explicit:

> `AUD-*/audit.db` is immutable execution evidence. Product, tenant, milestone, schedule, integration, cost and longitudinal metadata live in a separate control-plane database.

Neither control-plane backend changes `SARI-001` or `SCORE-GEO-004`.

## Supported persistence modes

```text
RASAi Product Platform
        |
        +-- SQLite
        |     local/default
        |     audits/.rasai/platform.db
        |
        +-- PostgreSQL 18
              explicit centralized/hosted target
```

SQLite is selected when no backend is configured.

PostgreSQL is selected explicitly with:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

A configured PostgreSQL backend never falls back silently to SQLite. `--platform-db` is a SQLite-only path override.

## Local Windows architecture

The local runtime is native Windows/Python. Docker is not required for SQLite operation.

```text
Windows
  rasai / rasai-console
        |
        +-- Audit / Quality / Monitor / Observability engine
        |      |
        |      +-- audits/AUD-*/audit.db      immutable evidence
        |      +-- audits/AUD-*/artifacts/    persisted evidence
        |
        +-- Product Platform
               |
               +-- audits/.rasai/platform.db  SQLite default
               +-- audits/platform-report/
               +-- audits/deployments/
```

The SQLite control plane uses foreign keys, WAL journaling, bounded busy timeout, explicit write transactions, stable opaque IDs, schema metadata, SHA-256 validation of indexed `audit.db` files and canonical multi-property scope links.

This mode is appropriate for single-machine/offline operation.

## PostgreSQL architecture

PostgreSQL 18 is the centralized control-plane backend. Local development can use a PostgreSQL 18 Docker container; the application itself consumes only the database connection contract.

```text
RASAi application
        |
RASAI_PLATFORM_DATABASE_URL
        |
PostgreSQL 18
```

PostgreSQL schema migration is explicit:

```powershell
rasai platform database status
rasai platform database migrate
```

Normal Product Platform/Search Monitoring startup does not create or upgrade PostgreSQL tables.

See `POSTGRESQL_CONTROL_PLANE.md` and `POSTGRESQL_MIGRATION_STRATEGY.md`.

## Data governance and authority

### Control plane

The selected relational backend is authoritative for:

- Organization / Workspace / Project;
- Property / Environment;
- users and memberships;
- external identity links;
- audit catalog and multi-property scope links;
- Milestones / Deployments;
- Golden Baselines;
- PageIdentity lineage;
- comparison records;
- schedules and alert rules;
- integration metadata without secrets;
- external datasets/outcomes;
- usage ledger and consumption analytics;
- Search Query Registry;
- Search monitoring run summaries;
- durable execution jobs.

In local mode this authority is `audits/.rasai/platform.db`. In PostgreSQL mode it is the configured PostgreSQL database.

### Derived analytical cache

```text
audits/.rasai/consolidated-index.db
```

When present, this is derived/rebuildable analytical state. It is not a second control plane and is not authoritative for tenancy, milestones, integrations, Query Registry or lifecycle state.

### Immutable audit evidence

```text
audits/AUD-*/audit.db
audits/AUD-*/artifacts/
```

These are source execution evidence regardless of the selected control-plane backend. Product metadata is not written back into an indexed AUD.

## Hosted SaaS target

The hosted operating model uses Linux/container workloads, managed PostgreSQL, durable scheduling/queueing and object storage.

```text
Web UI
  |
RASAi API / Control Plane
  |
  +-- managed PostgreSQL
  |      organization/workspace/project/property/environment
  |      memberships/RBAC metadata
  |      identity links
  |      milestones/deployments
  |      schedules/alerts/integrations
  |      Query Registry / monitoring runs
  |      usage ledger / audit catalog
  |      execution jobs
  |
  +-- durable Queue / Scheduler
  |      |
  |      +-- Linux audit workers
  |      +-- Search monitoring workers
  |      +-- integration workers
  |
  +-- Object Storage
         immutable AUD bundles / artifacts / reports / provider evidence

Optional enterprise path:
RASAi SaaS -> authorized Runner -> private Windows/Linux network
```

Linux is preferred for hosted workers because it provides predictable container packaging, Chromium/Playwright support, worker density, orchestration and broad cloud support. Native Windows remains the local/runner execution mode.

SQLite is appropriate for a local single-machine authority. SaaS requires centralized tenant state and concurrent transactional coordination, for which PostgreSQL is the production SGBD target.

The database transition boundary is the control plane, not the `AUD-*` evidence format.

## Product hierarchy

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
                  -> AuditRun references
                  -> Milestones
                  -> External datasets
                  -> Search monitoring contexts
```

- **Organization** - commercial/security tenant.
- **Workspace** - client, business unit or portfolio boundary.
- **Project** - logical Search & AI initiative; may contain multiple properties/domains.
- **Property** - owned or competitor web property identified by origin/hostname.
- **Environment** - `PRODUCTION`, `STAGING`, `QA`, `PREVIEW`, `DEVELOPMENT` or `OTHER`.

Stable opaque IDs are shared across SQLite/PostgreSQL domain contracts.

## Multi-user and tenant integrity

The control-plane model supports users, memberships and scoped roles.

Supported roles:

- `OWNER`;
- `ADMIN`;
- `ANALYST`;
- `OPERATOR`;
- `VIEWER`;
- `INTEGRATION_MANAGER`;
- `BILLING`.

Cross-organization memberships and inconsistent Project / Property / Environment writes are rejected at the control-plane boundary and backed by relational constraints.

Hosted identity is resolved through the Web/API authentication layer; control-plane persistence alone does not authenticate a request.

## Multi-domain AUD model

An AUD may contain more than one target origin/domain.

`audit_index` records the primary Property/Environment reference for the audit catalog, while `audit_scope_links` is the canonical many-to-many relation that makes the same AUD discoverable from every Property/Environment included in its scope.

```text
AUD
  -> Property A / Environment
  -> Property B / Environment
  -> Property C / Environment
```

Golden Baselines and deployment comparisons validate membership in the requested scope rather than relying only on the primary catalog reference.

## AUD immutability

The control-plane catalog stores the SHA-256 of every indexed `audit.db`.

Re-indexing an AUD with a different database hash is rejected. This prevents an indexed audit from being silently rewritten after it becomes a baseline or deployment evidence source.

PostgreSQL integration tests index SQLite `AUD-*/audit.db` files, perform Product Platform comparisons and verify the source audit bytes remain unchanged.

## Automatic indexing

A successful `rasai audit` triggers a best-effort refresh through the selected control-plane backend.

- the persisted AUD is authoritative evidence;
- product indexing cannot turn a successful audit into an audit failure;
- an indexing error is logged and can be repaired with `rasai platform index`.

When PostgreSQL is selected, its schema must already be current; automatic indexing never performs schema migration.

## Milestones and deployments

`Milestone` is a first-class product entity.

Supported kinds include:

- `DEPLOYMENT`;
- `RELEASE`;
- `CMS_MIGRATION`;
- `REDESIGN`;
- `CONTENT_RELEASE`;
- `SEO_CHANGE`;
- `INFRASTRUCTURE`;
- `INCIDENT`;
- `CAMPAIGN`;
- `MANUAL`;
- `OTHER`.

A milestone may record timestamp, release/version, commit SHA, branch/tag, description, tags and source.

## Before / after deployment resolution

Default mode: `AUTO`.

RASAi searches the same Property + Environment and selects:

1. the closest technically comparable AUD before the milestone;
2. the first technically comparable AUD after it.

If the nearest pair is not comparable, RASAi does not silently normalize incompatible data. Comparability limitations are retained.

Alternative modes:

- `GOLDEN` - approved Golden Baseline versus first compatible post-milestone AUD;
- `EXPLICIT` - operator-selected baseline/current pair.

Deployment Impact can display selected before/after AUDs, baseline resolution reason, material regressions, improvements/resolutions, changed page state, release gate result and comparability limitations.

Temporal ordering is not presented as causal proof.

## Page Compare and PageIdentity

`Page Compare` supports same-URL and migration/different-URL before/after analysis using persisted page-level signals.

`PageIdentity` separates a logical page/entity from one specific URL. Multiple observed URLs may be linked to the same identity for redirects, URL changes and replatforming.

## Portfolio HTML

`rasai platform site` generates Product Platform projections including:

- Portfolio index;
- timeline;
- deployments;
- page lineage;
- usage/cost views.

Property counters resolve through canonical multi-property AUD scopes.

These pages remain separate from the report site contained inside one immutable AUD.

## Scheduling

Schedules store argument arrays, never raw shell strings.

Execution uses:

```text
<current-python> -m rasai <argv...>
```

with `shell=False`.

Supported schedule semantics include:

- `INTERVAL`;
- `DAILY`;
- `MANUAL`;
- `DEPLOYMENT_TRIGGERED`;
- `API_TRIGGERED`.

Local execution is single-machine. PostgreSQL-backed scheduling is centralized, while horizontally distributed execution additionally requires atomic occurrence claiming, leases/locks, idempotency, retry/dead-letter state and per-tenant/provider limits.

## Search monitoring

`SEARCH-MONITOR-001` uses the selected Product Platform control-plane authority.

```text
Query Registry
  -> schedule
  -> Search observation
  -> deterministic/optional AI intelligence
  -> longitudinal run summary
  -> change detection
```

SQLite is the local adapter. PostgreSQL is the centralized adapter. Raw provider evidence and hashed manifests remain outside relational rows and move naturally to object storage in hosted operation.

Search monitoring is non-scoring.

## Alerts

Alert rules evaluate material comparison events by status and minimum severity.

Default statuses when no `--status` is supplied:

```text
REGRESSED
NEW
```

Explicit `--status` values replace the defaults.

Destinations:

- `NONE` - persist notification only;
- `JSON` - persist structured notification;
- `WEBHOOK` - POST structured JSON.

Webhook secrets are not stored as ordinary product metadata. Hosted delivery requires managed secrets and SSRF/egress controls.

## CI/CD release-gate outputs

Deployment comparisons can export JSON, JUnit XML and SARIF, with process exit semantics suitable for CI/CD integration.

The contract is vendor-neutral.

## External outcomes and crawler observability

External observations remain outside SARI/SCORE-GEO.

Sources include:

- GA4 Data API using bearer token from runtime environment;
- GA4 CSV import;
- Cloudflare Logpush import;
- common/combined Apache/nginx-compatible access logs;
- explicit User-Agent marker classification for known AI crawler markers.

Crawler classification is evidence classification, not proof of verified bot identity. Verified provider/CDN bot-management signals should supersede heuristic identity where available.

## Usage ledger and consumption analytics

Product consumption is stored separately from technical findings, including categories such as:

- URLs crawled;
- browser executions;
- API calls;
- LLM/provider consumption;
- worker/storage units when implemented;
- estimated cost/currency.

The same ledger supports consumption analytics and future SaaS metering while preserving provenance/BYOK attribution.

## Secrets

No API token, webhook secret or provider password is stored as plain product metadata.

Local operation uses environment variables and persists only non-secret configuration or secret-reference names.

Hosted operation uses managed secret storage/KMS-backed services, tenant-scoped authorization and rotation/audit controls.

`RASAI_PLATFORM_DATABASE_URL` is secret-bearing and must be redacted from status/error output.

## Docker decision

Docker is not required for normal SQLite Windows operation. It is used for local PostgreSQL 18 development/integration and PostgreSQL CI.

For hosted deployment, API/workers may be containerized; production PostgreSQL should normally be managed rather than coupled to one application container host.

## PostgreSQL schema strategy

The PostgreSQL schema uses the domain representation expected by current repository contracts. Representation changes are explicit schema migrations and are validated for semantic parity.

Development SQLite data is test/pilot state and is not a required migration source for a clean PostgreSQL authority.

## Primary CLI examples

SQLite initialization/index:

```powershell
rasai platform --audits-root audits init
rasai platform --audits-root audits index
rasai platform --audits-root audits status
rasai platform --audits-root audits data status
rasai platform --audits-root audits site
```

PostgreSQL administration:

```powershell
rasai platform database status
rasai platform database migrate
rasai platform database status
```

Users and memberships:

```powershell
rasai platform --audits-root audits user add --name "Analyst" --email analyst@example.com
rasai platform --audits-root audits member add `
  --organization ORG-... --user USR-... --role ANALYST `
  --workspace WSP-... --project PRJ-...
```

Create a deployment milestone:

```powershell
rasai platform --audits-root audits milestone add `
  --project PRJ-... `
  --property PTY-... `
  --environment ENV-... `
  --kind DEPLOYMENT `
  --at 2026-09-07T14:35:00-03:00 `
  --title "Release 3.12" `
  --release 3.12.0 `
  --commit abc123
```

Resolve/compare:

```powershell
rasai platform --audits-root audits deploy pair --milestone MLS-...

rasai platform --audits-root audits deploy compare `
  --milestone MLS-... `
  --json artifacts/gate.json `
  --junit artifacts/gate.xml `
  --sarif artifacts/gate.sarif
```

Golden baseline:

```powershell
rasai platform --audits-root audits baseline set `
  --property PTY-... --environment ENV-... --audit AUD-...
```

Page Compare:

```powershell
rasai platform --audits-root audits page compare `
  --baseline AUD-BEFORE `
  --current AUD-AFTER `
  --baseline-url https://example.com/produto `
  --output page-compare.html
```

## Operational boundary

Audit, Monitor, Quality, Observability and Visibility use the same immutable-evidence boundary regardless of the selected Product Platform backend.

Post-audit platform indexing is best-effort and fail-open, so a control-plane indexing problem cannot invalidate an already persisted audit.

## Methodological boundary

Product/portfolio data, Search monitoring, GA4, logs, milestones, deployment markers, schedules and usage do not alter SARI/SCORE-GEO by default.

Temporal association is not causal inference. The platform may state that a technical change and an observed outcome occurred in a defined temporal relationship; it must not claim the deployment caused the outcome unless a separate validated causal method establishes that conclusion.
