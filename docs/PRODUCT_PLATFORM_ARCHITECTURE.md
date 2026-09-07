# RASAI Product Platform Architecture

Status: implementation branch `feat/rasai-product-platform-architecture`.

## Objective

Evolve RASAI from a single-audit Windows application into a product platform that supports multi-user, multi-client, multi-project and multi-domain operation without breaking the current audit engine or rewriting historical evidence.

The architectural rule is explicit:

> `AUD-*/audit.db` remains immutable execution evidence. Product, tenant, milestone, schedule, integration, cost and longitudinal metadata live in a separate control-plane database.

## Current local architecture — Windows first

The supported local runtime remains native Windows/Python. Docker is **not** required.

```text
Windows
  rasai / rasai-console
        |
        +-- existing Audit / Quality / Monitor / Observability engine
        |      |
        |      +-- audits/AUD-*/audit.db      immutable evidence
        |      +-- audits/AUD-*/artifacts/    persisted evidence
        |
        +-- Product Platform
               |
               +-- audits/.searchgeo/platform.db
               +-- audits/platform-report/
               +-- audits/deployments/
```

`platform.db` uses SQLite with:

- foreign keys enabled;
- WAL journaling;
- `synchronous=NORMAL`;
- `busy_timeout`;
- explicit write transactions;
- stable opaque IDs;
- schema version metadata;
- SHA-256 of every indexed `audit.db`.

This is appropriate for the single-machine Windows phase. It is **not** the intended final SaaS SGBD.

## SaaS target architecture

For SaaS, the recommended operating model is Linux-based container workloads with a managed PostgreSQL control plane.

```text
Web UI
  |
RASAI API / Control Plane
  |
  +-- PostgreSQL
  |      organization/workspace/project/property/environment
  |      memberships/RBAC
  |      milestones/deployments
  |      schedules/alerts/integrations
  |      usage ledger
  |      audit catalog
  |
  +-- Queue / Scheduler
  |      |
  |      +-- Linux audit workers (containerized)
  |      +-- integration workers
  |
  +-- Object Storage
         immutable AUD bundles / artifacts / reports

Optional Enterprise path:
RASAI SaaS -> authorized Runner -> Windows/Linux private network
```

### Why Linux for SaaS workers

Linux is preferred for the hosted execution plane because it provides a simpler container runtime, predictable Chromium/Playwright packaging, lower worker density cost, mature orchestration and standard cloud support.

This does **not** replace Windows local support. The product keeps two execution modes:

1. native Windows Desktop/CLI/Runner;
2. Linux container worker for hosted SaaS workloads.

### Why PostgreSQL for SaaS

SQLite remains correct for a local single-machine control plane. SaaS adds concurrency, tenant isolation, transactions across concurrent workers, connection pooling, backup/restore, replication and operational observability. PostgreSQL is therefore the preferred production SGBD.

The migration boundary is the product control plane, not the `AUD-*` evidence format.

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
```

### Organization

Commercial/security tenant.

### Workspace

Client, business unit or portfolio boundary. An agency can use one workspace per client; an enterprise can use one per business unit.

### Project

Logical Search & AI initiative. It may contain multiple properties/domains.

### Property

Owned or competitor web property, identified by canonical origin/hostname.

### Environment

Formal deployment surface: `PRODUCTION`, `STAGING`, `QA`, `PREVIEW`, `DEVELOPMENT` or `OTHER`.

## AUD immutability

The platform catalog stores the SHA-256 of every indexed `audit.db`.

Re-indexing an AUD with a different database hash is rejected. This prevents a historical audit from being silently rewritten after it has become a baseline or deployment evidence source.

New operational metadata is never written into the historical `audit.db`.

## Automatic indexing

A successful `rasai audit` triggers a best-effort refresh of `platform.db` through the top-level command router.

This is intentionally fail-open:

- successful audit persistence remains authoritative;
- product indexing cannot convert a successful audit into a failure;
- an indexing error is logged and can be repaired with `rasai platform index`.

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

A deployment may record:

- timestamp;
- release/version;
- commit SHA;
- branch/tag;
- description;
- tags;
- source (`MANUAL`, CI/CD, API in future).

## Before / after deployment resolution

Default mode: `AUTO`.

RASAI searches the same Property + Environment and selects:

1. the closest technically comparable AUD before the milestone;
2. the first technically comparable AUD after it.

If the nearest pair is not comparable, RASAI does not silently normalize incompatible data. Compatibility notes are retained.

Alternative modes:

- `GOLDEN`: approved Golden Baseline versus first compatible post-milestone AUD;
- `EXPLICIT`: operator-selected baseline/current AUD pair.

## Deployment Impact

The Deployment Impact report reuses the existing deterministic monitoring comparison and release gate.

It displays:

- selected before/after AUDs;
- baseline resolution reason;
- material regressions;
- improvements/resolutions;
- changed page state;
- release gate PASS/FAIL;
- comparability limitations.

The report does not claim that a later business/Search outcome was caused by the deploy merely because it occurred afterwards.

## Page Compare and PageIdentity

`Page Compare` supports:

- same URL before/after;
- different URL before/after, useful for migration;
- persisted page-level rule/page-state signals.

`PageIdentity` separates a logical page/entity from one specific URL. Multiple historical URLs may be linked to the same page identity for redirects and replatforming.

## Portfolio HTML

`rasai platform site` generates a product-level HTML set:

- `index.html` — Portfolio;
- `timeline.html` — AUD + milestone timeline;
- `deployments.html` — deployments/releases;
- `pages.html` — page lineage;
- `usage.html` — usage/cost ledger.

These pages use the current RASAI visual language but are intentionally separate from the menu inside a single AUD report.

## Scheduling

The local scheduler stores argument arrays, never raw shell command strings.

Execution uses:

```text
<current-python> -m searchgeo <argv...>
```

with `shell=False`.

This avoids shell-command interpolation and works on Windows without Docker.

Supported schedule semantics:

- `INTERVAL`;
- `DAILY`;
- `MANUAL`;
- `DEPLOYMENT_TRIGGERED`;
- `API_TRIGGERED`.

The local implementation executes due schedules when `rasai platform schedule run-due` is invoked. Windows Task Scheduler can invoke this command periodically. SaaS will replace the polling host with a central scheduler/queue while preserving schedule records.

## Alerts

Alert rules evaluate material comparison events by status and minimum severity.

Current destinations:

- `NONE` — persist notification only;
- `JSON` — persist structured notification;
- `WEBHOOK` — POST structured JSON.

Webhook URLs are not stored in `platform.db`. Only an environment-variable name is persisted. Non-local webhooks require HTTPS.

Future SaaS delivery should add SSRF protections, outbound allow policies and managed secret storage.

## CI/CD release gate outputs

Deployment comparisons can export:

- JSON;
- JUnit XML;
- SARIF 2.1.0;
- process exit code (`0=PASS`, `1=gate FAIL`, `2=operational error`).

This supports GitHub Actions, Azure DevOps, Jenkins and other CI/CD products without coupling RASAI to one vendor.

## External outcomes and crawler observability

External observations stay outside SARI/SCORE-GEO.

Implemented product-platform sources:

### GA4 Data API

Official `runReport` collection using a bearer token read from an environment variable. RASAI does not persist the bearer token.

### GA4 CSV

Import-first path for controlled exports and offline/local operation.

### Cloudflare Logpush

Imports HTTP request JSON/JSONL exports and preserves raw fields inside metadata.

### Generic access logs

Imports common/combined Apache/nginx-compatible request lines.

### AI crawler classification

Initial crawler classification is an explicit User-Agent marker heuristic for known markers such as OAI-SearchBot, GPTBot, ChatGPT-User, ClaudeBot and PerplexityBot. It is evidence classification, not proof of verified bot identity.

For SaaS/Enterprise, verified provider signals or CDN bot-management identifiers should supersede heuristic identity where available.

## Usage ledger

The platform stores product consumption separately from technical findings:

- URLs crawled;
- browser executions;
- API calls;
- LLM tokens;
- external provider usage;
- storage/worker units in future;
- estimated costs and currency.

This supports future SaaS pricing while preserving BYOK attribution.

## Secrets

No API token, webhook URL or provider password should be stored as plain product metadata.

Local phase:

- environment variables;
- integration records store only the environment variable name.

SaaS phase:

- managed secret store / KMS-backed secret manager;
- tenant-scoped authorization;
- rotation/audit trail.

## Docker decision

Docker is intentionally **not a local requirement** in the current release.

Docker should be introduced when at least one of these becomes true:

1. hosted Linux audit workers are implemented;
2. PostgreSQL integration tests are required;
3. queue/broker integration is introduced;
4. reproducible cloud-worker images are required;
5. local developer integration needs a disposable SaaS stack.

At that point, recommended development topology:

```text
docker compose
  api/control-plane
  worker
  postgres
  optional queue
```

The native Windows CLI must continue working without Docker.

## SGBD migration contract

`platform.db` is the local control-plane implementation. SaaS migration should map the same stable domain contracts to PostgreSQL.

Do not migrate historical AUD evidence into mutable relational tables merely to centralize storage. Store immutable AUD bundles in object storage and index their metadata in PostgreSQL.

Suggested SaaS PostgreSQL concerns:

- tenant key on all tenant-owned records;
- row-level authorization policy at service layer and, where useful, PostgreSQL RLS;
- connection pooling;
- migration tool with forward-only schema revisions;
- audit trail for control-plane changes;
- backup/PITR;
- encrypted storage and TLS;
- unique constraints scoped by tenant/workspace/project;
- partitioning only after measured need.

## Primary CLI examples

Initialize/index:

```powershell
rasai platform --audits-root audits init
rasai platform --audits-root audits index
rasai platform --audits-root audits status
rasai platform --audits-root audits site
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

GA4 import/API:

```powershell
rasai platform --audits-root audits collect ga4-csv `
  --property PTY-... --environment ENV-... --file ga4.csv

$env:GOOGLE_ANALYTICS_ACCESS_TOKEN="..."
rasai platform --audits-root audits collect ga4 `
  --property PTY-... --environment ENV-... `
  --ga4-property 123456789 `
  --start-date 2026-08-01 --end-date 2026-08-31
```

Logs:

```powershell
rasai platform --audits-root audits collect cloudflare-logpush `
  --property PTY-... --environment ENV-... --file cf.jsonl

rasai platform --audits-root audits collect access-log `
  --property PTY-... --environment ENV-... --file access.log
```

## Compatibility contract

Existing commands remain unchanged:

- `rasai audit`;
- `rasai monitor`;
- `rasai quality`;
- `rasai observability`;
- `rasai visibility`;
- legacy `searchgeo` command aliases.

The new surface is additive under `rasai platform`.

## Methodological boundary

Product/portfolio data, GA4, logs, milestones, deployment markers, schedules and usage do not alter SARI/SCORE-GEO by default.

Temporal association is not causal inference.

The platform may state that a technical change and an observed outcome occurred in a defined temporal relationship. It must not claim the deploy caused the outcome unless a separate validated causal method establishes that conclusion.
