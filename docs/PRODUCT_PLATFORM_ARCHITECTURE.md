# RASAi Product Platform Architecture

Status: implemented product-platform architecture with SQLite local/default persistence and an explicit PostgreSQL 18 control-plane backend under cross-platform regression validation.

## Objective

Evolve RASAi from a single-audit Windows application into a product platform that supports multi-user, multi-client, multi-project and multi-domain operation without breaking the audit engine or rewriting historical evidence.

The architectural rule is explicit:

> `AUD-*/audit.db` remains immutable execution evidence. Product, tenant, milestone, schedule, integration, cost and longitudinal metadata live in a separate control-plane database.

Neither control-plane backend changes `SARI-001` or `SCORE-GEO-004`.

## Supported persistence modes

The control plane now has two persistence implementations behind one composition boundary:

```text
RASAi Product Platform
        |
        +-- SQLite
        |     local/default
        |     audits/.rasai/platform.db
        |
        +-- PostgreSQL 18
              explicit opt-in
              centralized / hosted target
```

SQLite remains the default when no backend is configured. Existing Windows/local operation therefore keeps its current installation and runtime behavior.

PostgreSQL is selected explicitly with:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

A configured PostgreSQL backend never falls back silently to SQLite.

`--platform-db` remains a SQLite-only path override.

## Local Windows architecture

The supported local runtime remains native Windows/Python. Docker is not required to run RASAi in its default SQLite mode.

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

This remains appropriate for single-machine/offline operation.

## PostgreSQL development architecture

PostgreSQL 18 is the centralized control-plane backend. Local development uses a PostgreSQL 18 Docker container; the application itself is not coupled to Docker and only consumes the database connection contract.

```text
Windows/Python RASAi
        |
RASAI_PLATFORM_DATABASE_URL
        |
PostgreSQL 18
```

Docker is therefore a **developer integration dependency for PostgreSQL work**, not a new requirement for users who remain on the default SQLite runtime.

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
- audit catalog and multi-property scope links;
- Milestones / Deployments;
- Golden Baselines;
- PageIdentity lineage;
- comparison records;
- schedules and alert rules;
- integration metadata without secrets;
- external datasets/outcomes;
- usage ledger;
- Search Query Registry;
- Search monitoring run summaries.

In local/default mode this authority is `audits/.rasai/platform.db`. In PostgreSQL mode the configured PostgreSQL database is the authority.

### Historical analytical cache

```text
audits/.rasai/consolidated-index.db
```

When present, this remains a derived/rebuildable compatibility cache for historical consolidated reporting. It is not a second control plane and must not become authoritative for tenancy, milestones, integrations, Query Registry or lifecycle state.

### Immutable audit evidence

```text
audits/AUD-*/audit.db
audits/AUD-*/artifacts/
```

These remain source execution evidence regardless of the selected control-plane backend. Product metadata is never written back into an indexed historical AUD.

## Hosted SaaS target

The recommended hosted operating model remains Linux/container workloads with managed PostgreSQL, durable scheduling/queueing and object storage.

```text
Web UI
  |
RASAi API / Control Plane
  |
  +-- managed PostgreSQL
  |      organization/workspace/project/property/environment
  |      memberships/RBAC metadata
  |      milestones/deployments
  |      schedules/alerts/integrations
  |      Query Registry / monitoring runs
  |      usage ledger / audit catalog
  |
  +-- durable Queue / Scheduler
  |      |
  |      +-- Linux audit workers
  |      +-- Search monitoring workers
  |      +-- integration workers
  |
  +-- Object Storage
         immutable AUD bundles / artifacts / reports / provider evidence

Optional Enterprise path:
RASAi SaaS -> authorized Runner -> private Windows/Linux network
```

### Why Linux for hosted workers

Linux is preferred for the hosted execution plane because it provides predictable container packaging, Chromium/Playwright support, worker density, orchestration and broad cloud support.

This does not replace Windows local support. The product keeps distinct execution modes:

1. native Windows Desktop/CLI/Runner;
2. Linux container workers for hosted workloads.

### Why PostgreSQL for the hosted control plane

SQLite remains correct for a local single-machine authority. SaaS requires concurrency, centralized tenant state, transactional coordination, backup/restore, connection management and operational observability. PostgreSQL is the production SGBD target.

The migration boundary is the control plane, not the `AUD-*` evidence format.

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

The control-plane model supports users, memberships and scoped roles so the same domain contracts can be used by a future authenticated SaaS API.

Supported roles:

- `OWNER`;
- `ADMIN`;
- `ANALYST`;
- `OPERATOR`;
- `VIEWER`;
- `INTEGRATION_MANAGER`;
- `BILLING`.

Cross-organization memberships and inconsistent Project / Property / Environment writes are rejected at the control-plane boundary and backed by relational constraints.

This is data-model readiness, not a claim that the current CLI already provides hosted authentication/network identity.

## Multi-domain AUD model

An AUD may contain more than one target origin/domain. For backward compatibility, `audit_index` retains one primary Property/Environment. The canonical relation is additive:

```text
AUD
  -> Property A / Environment
  -> Property B / Environment
  -> Property C / Environment
```

`audit_scope_links` makes a multidomain AUD discoverable from every linked Property/Environment.

Golden Baselines and deployment comparisons validate membership in the requested scope rather than relying only on the legacy primary property.

## AUD immutability

The control-plane catalog stores the SHA-256 of every indexed `audit.db`.

Re-indexing an AUD with a different database hash is rejected. This prevents a historical audit from being silently rewritten after it becomes a baseline or deployment evidence source.

PostgreSQL integration tests explicitly index SQLite `AUD-*/audit.db` files, perform Product Platform comparisons and verify the source audit bytes are unchanged.

## Automatic indexing

A successful `rasai audit` triggers a best-effort refresh through the selected control-plane backend.

This remains intentionally fail-open relative to successful audit persistence:

- the persisted AUD is authoritative evidence;
- product indexing cannot turn a successful audit into an audit failure;
- an indexing error is logged and can be repaired with `rasai platform index`.

When PostgreSQL is selected, the PostgreSQL schema must already be current; automatic indexing is not allowed to perform schema migration.

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

If the nearest pair is not comparable, RASAi does not silently normalize incompatible data. Compatibility notes are retained.

Alternative modes:

- `GOLDEN` - approved Golden Baseline versus first compatible post-milestone AUD;
- `EXPLICIT` - operator-selected baseline/current pair.

## Deployment Impact

Deployment Impact reuses deterministic monitoring comparison and release-gate contracts.

It can display:

- selected before/after AUDs;
- baseline resolution reason;
- material regressions;
- improvements/resolutions;
- changed page state;
- release gate PASS/FAIL;
- comparability limitations.

Deployment reports are standalone artifacts. They do not claim that a later Search/business outcome was caused by the deployment merely because it occurred afterwards.

## Page Compare and PageIdentity

`Page Compare` supports same-URL and migration/different-URL before/after analysis using persisted page-level signals.

`PageIdentity` separates a logical page/entity from one specific URL. Multiple historical URLs may be linked to the same identity for redirects and replatforming.

## Portfolio HTML

`rasai platform site` generates Product Platform projections including:

- Portfolio index;
- timeline;
- deployments;
- page lineage;
- usage/cost views.

Property counters resolve through canonical multi-property AUD scopes rather than only the legacy primary property.

These pages remain separate from the menu inside one immutable AUD report.

## Scheduling

The local scheduler stores argument arrays, never raw shell strings.

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

Local execution remains single-machine. Persisting schedules in PostgreSQL does not automatically make scheduling horizontally safe.

The future hosted scheduler/queue must add atomic occurrence claiming, leases/locks, idempotency, retry/dead-letter state and per-tenant/provider limits before multiple scheduler/worker replicas are used.

## Search monitoring

`SEARCH-MONITOR-001` uses the same selected control-plane authority as Product Platform.

```text
Query Registry
  -> schedule
  -> Search observation
  -> deterministic/optional AI intelligence
  -> longitudinal run summary
  -> change detection
```

SQLite remains the local/default adapter. PostgreSQL provides the centralized adapter. Raw provider evidence and hashed manifests remain outside relational rows and can move to object storage in hosted operation.

Search monitoring remains non-scoring.

## Alerts

Alert rules evaluate material comparison events by status and minimum severity.

Default statuses when no `--status` is supplied:

```text
REGRESSED
NEW
```

Explicit `--status` values replace the defaults.

Current destinations:

- `NONE` - persist notification only;
- `JSON` - persist structured notification;
- `WEBHOOK` - POST structured JSON.

Webhook URLs are not stored as ordinary control-plane values; only the environment-variable reference is persisted locally. Hosted delivery still requires managed secrets and SSRF/egress controls.

## CI/CD release-gate outputs

Deployment comparisons can export JSON, JUnit XML and SARIF, with process exit semantics suitable for CI/CD integration.

This remains vendor-neutral and does not couple RASAi to one CI system.

## External outcomes and crawler observability

External observations remain outside SARI/SCORE-GEO.

Implemented sources include:

- GA4 Data API using bearer token from runtime environment;
- GA4 CSV import-first path;
- Cloudflare Logpush import;
- common/combined Apache/nginx-compatible access logs;
- explicit User-Agent marker classification for known AI crawler markers.

Crawler classification is evidence classification, not proof of verified bot identity. Verified provider/CDN bot-management signals should supersede heuristic identity where available.

## Usage ledger

Product consumption is stored separately from technical findings, including categories such as:

- URLs crawled;
- browser executions;
- API calls;
- LLM/provider consumption;
- future worker/storage units;
- estimated cost/currency.

This supports future SaaS metering while preserving provenance/BYOK attribution.

## Secrets

No API token, webhook secret or provider password should be stored as plain product metadata.

Local phase:

- environment variables;
- database rows persist only non-secret configuration or secret-reference names.

Hosted phase:

- managed secret store / KMS-backed service;
- tenant-scoped authorization;
- rotation/audit trail.

`RASAI_PLATFORM_DATABASE_URL` is also a secret-bearing runtime value. Status/error output must redact its password.

## Docker decision

Docker has two distinct roles:

1. **not required** for the normal SQLite Windows runtime;
2. **used** for local PostgreSQL 18 integration/development and PostgreSQL CI.

The local PostgreSQL container is development infrastructure, not the intended production database.

The future hosted environment may use containerized API/workers, but production PostgreSQL should normally be a managed service rather than a database container tied to one application host.

## PostgreSQL schema strategy

The initial PostgreSQL schema is compatibility-first. It preserves current domain serialization where changing representation at the same time as the database engine would add unnecessary migration risk.

PostgreSQL-native JSON/boolean/time types can be introduced later through versioned migrations and parity tests. See `POSTGRESQL_CONTROL_PLANE.md` for the current schema contract.

Existing SQLite data is test-only and is not a required migration source for the first PostgreSQL authority.

## Primary CLI examples

SQLite/default initialization/index:

```powershell
rasai platform --audits-root audits init
rasai platform --audits-root audits index
rasai platform --audits-root audits status
rasai platform --audits-root audits data status
rasai platform --audits-root audits site
```

PostgreSQL schema administration after setting the PostgreSQL backend environment:

```powershell
rasai platform database status
rasai platform database migrate
rasai platform database status
```

The same Product Platform commands then operate against PostgreSQL through backend composition.

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

GA4/log imports continue through the same `rasai platform collect ...` surface.

## Compatibility contract

Existing audit/monitor/quality/observability/visibility behavior remains unchanged. The Product Platform database choice is a control-plane concern.

The post-audit platform-index refresh remains best-effort and fail-open, so control-plane indexing problems cannot invalidate a successfully persisted audit.

## Methodological boundary

Product/portfolio data, Search monitoring, GA4, logs, milestones, deployment markers, schedules and usage do not alter SARI/SCORE-GEO by default.

Temporal association is not causal inference. The platform may state that a technical change and an observed outcome occurred in a defined temporal relationship; it must not claim the deployment caused the outcome unless a separate validated causal method establishes that conclusion.