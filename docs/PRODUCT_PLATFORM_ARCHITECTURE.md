# RASAi Product Platform Architecture

Status: implemented product-platform architecture. Merge readiness is determined by automated Windows/Linux validation and regression gates.

## Objective

Evolve RASAi from a single-audit Windows application into a product platform that supports multi-user, multi-client, multi-project and multi-domain operation without breaking the current audit engine or rewriting historical evidence.

The architectural rule is explicit:

> `AUD-*/audit.db` remains immutable execution evidence. Product, tenant, milestone, schedule, integration, cost and longitudinal metadata live in a separate control-plane database.

## Current local architecture - Windows first

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
               +-- audits/.rasai/platform.db
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
- SHA-256 of every indexed `audit.db`;
- additive canonical extensions for multi-property AUD scopes.

This is appropriate for the single-machine Windows phase. It is **not** the intended final SaaS SGBD.

## Local data governance and database roles

RASAi can have more than one local SQLite database, but they do **not** have equal authority.

### Canonical control plane

```text
audits/.rasai/platform.db
```

This is the authoritative product/control-plane database for:

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
- usage ledger.

### Legacy consolidated analytical cache

```text
audits/.rasai/consolidated-index.db
```

When present, this remains a **derived, rebuildable compatibility/analytical cache** used by the historical consolidated-reporting surface. It is not a second control plane and must not become authoritative for tenancy, milestones, integrations or lifecycle metadata.

Use:

```powershell
rasai platform --audits-root audits data status
```

to inspect the local data-governance roles.

### Immutable audit evidence

```text
audits/AUD-*/audit.db
audits/AUD-*/artifacts/
```

These remain the source execution evidence. Product-platform metadata is never written back into historical AUD databases.

## SaaS target architecture

For SaaS, the recommended operating model is Linux-based container workloads with a managed PostgreSQL control plane.

```text
Web UI
  |
RASAi API / Control Plane
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
RASAi SaaS -> authorized Runner -> Windows/Linux private network
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

- **Organization** - commercial/security tenant.
- **Workspace** - client, business unit or portfolio boundary.
- **Project** - logical Search & AI initiative; may contain multiple properties/domains.
- **Property** - owned or competitor web property identified by origin/hostname.
- **Environment** - `PRODUCTION`, `STAGING`, `QA`, `PREVIEW`, `DEVELOPMENT` or `OTHER`.

## Multi-user and tenant integrity

The Windows-local database already models users, memberships and scoped roles so the domain contracts survive the SaaS migration.

Supported roles:

- `OWNER`;
- `ADMIN`;
- `ANALYST`;
- `OPERATOR`;
- `VIEWER`;
- `INTEGRATION_MANAGER`;
- `BILLING`.

Cross-organization memberships and inconsistent Project / Property / Environment writes are rejected at the control-plane boundary.

This is data-model readiness, not a claim that the current Windows CLI already implements SaaS authentication or network identity.

## Multi-domain AUD model

An AUD may contain more than one target origin/domain. For backward compatibility, `audit_index` retains one primary Property/Environment. The canonical relation is additive:

```text
AUD
  -> Property A / Environment
  -> Property B / Environment
  -> Property C / Environment
```

`audit_scope_links` is used by product-platform functions so a multidomain AUD is discoverable from every linked Property/Environment.

Golden Baselines and deploy comparisons validate membership in the requested scope instead of relying only on the legacy primary property.

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

A deployment may record timestamp, release/version, commit SHA, branch/tag, description, tags and source.

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

The Deployment Impact report reuses the existing deterministic monitoring comparison and release gate.

It displays:

- selected before/after AUDs;
- baseline resolution reason;
- material regressions;
- improvements/resolutions;
- changed page state;
- release gate PASS/FAIL;
- comparability limitations.

Deployment reports are standalone artifacts under their own output directory. They do not emit relative menu links that presume they are stored inside the Portfolio directory.

The report does not claim that a later business/Search outcome was caused by the deploy merely because it occurred afterwards.

## Page Compare and PageIdentity

`Page Compare` supports:

- same URL before/after;
- different URL before/after for migrations;
- persisted page-level rule/page-state signals.

`PageIdentity` separates a logical page/entity from one specific URL. Multiple historical URLs may be linked to the same page identity for redirects and replatforming.

## Portfolio HTML

`rasai platform site` generates:

- `index.html` - Portfolio;
- `timeline.html` - AUD + milestone timeline;
- `deployments.html` - deployments/releases;
- `pages.html` - page lineage;
- `usage.html` - usage/cost ledger.

Property counters resolve through canonical multi-property AUD scopes rather than only the legacy primary property.

These pages use the current RASAi visual language but are intentionally separate from the menu inside a single AUD report.

## Scheduling

The local scheduler stores argument arrays, never raw shell command strings.

Execution uses:

```text
<current-python> -m rasai <argv...>
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

Default statuses when no `--status` is supplied:

```text
REGRESSED
NEW
```

When one or more `--status` values are supplied explicitly, they **replace** the defaults instead of being appended to them.

Current destinations:

- `NONE` - persist notification only;
- `JSON` - persist structured notification;
- `WEBHOOK` - POST structured JSON.

Webhook URLs are not stored in `platform.db`. Only an environment-variable name is persisted. Non-local webhooks require HTTPS.

Future SaaS delivery should add SSRF protections, outbound allow policies and managed secret storage.

## CI/CD release gate outputs

Deployment comparisons can export:

- JSON;
- JUnit XML;
- SARIF 2.1.0;
- process exit code (`0=PASS`, `1=gate FAIL`, `2=operational error`).

This supports GitHub Actions, Azure DevOps, Jenkins and other CI/CD products without coupling RASAi to one vendor.

## External outcomes and crawler observability

External observations stay outside SARI/SCORE-GEO.

Implemented product-platform sources:

### GA4 Data API

Official `runReport` collection using a bearer token read from an environment variable. RASAi does not persist the bearer token.

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

Recommended future development topology:

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
- row-level authorization at service layer and, where useful, PostgreSQL RLS;
- connection pooling;
- forward-only schema revisions;
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
rasai platform --audits-root audits data status
rasai platform --audits-root audits site
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
- legacy `rasai` command aliases.

The new surface is additive under `rasai platform`.

The post-audit platform-index refresh is best-effort and fail-open, so a control-plane indexing problem cannot turn a successfully persisted audit into an audit failure.

## Methodological boundary

Product/portfolio data, GA4, logs, milestones, deployment markers, schedules and usage do not alter SARI/SCORE-GEO by default.

Temporal association is not causal inference.

The platform may state that a technical change and an observed outcome occurred in a defined temporal relationship. It must not claim the deploy caused the outcome unless a separate validated causal method establishes that conclusion.
