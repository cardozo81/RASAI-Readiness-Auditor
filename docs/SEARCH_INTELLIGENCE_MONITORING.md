# Search Intelligence Monitoring

Status: implemented control-plane monitoring contract with SQLite local/default and PostgreSQL explicit opt-in adapters.

Current contract:

```text
SEARCH-MONITOR-001
```

Search Intelligence Monitoring turns a manually supplied Search query into a registered, repeatable observation context. It is operational and longitudinal; it does not create a new readiness score and does not alter `SARI-001` or `SCORE-GEO-004`.

## Purpose

A registered query preserves the context required for repeatable observation:

- Project, Property and Environment;
- query text;
- domain of interest;
- Search engine;
- country/market;
- optional region;
- language;
- device;
- requested depth;
- Search provider and acquisition mode;
- deterministic competitive-analysis controls;
- optional bounded public-content comparison;
- optional evidence-bound Competitive AI controls;
- enabled/disabled state;
- optional recurring schedule.

The registered context is the unit of longitudinal comparison. RASAi does not silently compare runs that changed provider or data mode.

## Data authority and immutable audit evidence

Recurring Search monitoring must not append observations to historical audit databases.

The authority split in local/default mode is:

```text
AUD-*/audit.db
  immutable point-in-time audit evidence

.rasai/platform.db
  SQLite product/control-plane metadata
  registered Search queries
  longitudinal Search run summaries
  schedules

.rasai/search-monitoring/
  raw Search provider evidence
  run manifests and SHA-256 integrity metadata
```

When PostgreSQL is explicitly selected, the relational portion changes to:

```text
PostgreSQL control plane
  Product Platform relational state
  registered Search queries
  longitudinal Search run summaries
  schedules

.rasai/search-monitoring/ or future object storage
  raw Search provider evidence
  run manifests and SHA-256 integrity metadata
```

PostgreSQL does not change the immutable `AUD-*/audit.db` evidence contract.

## Control-plane persistence

The relational Search monitoring tables are:

```text
search_monitor_queries
search_monitor_runs
```

`search_monitor_queries` references the existing Product Platform hierarchy and schedule model. It does not create an independent Project/Domain hierarchy.

`search_monitor_runs` stores longitudinal run summaries including:

- run and observation IDs;
- collection timestamps;
- Search provider and data mode;
- domain status and observed customer position;
- result count;
- domains observed ahead of the customer;
- raw evidence reference and SHA-256;
- deterministic comparison state and gap codes;
- customer content coverage signals when observed;
- observed word count and JSON-LD types;
- Competitive AI state/provider/model/opportunity count when enabled;
- change events against the previous comparable run;
- SERP/content/AI request counters;
- run manifest reference and SHA-256;
- error state when applicable.

The runtime is behind the `SearchMonitoringRepository` contract. SQLite is the default local adapter and PostgreSQL implements the same domain behavior for the centralized control plane. Backend selection occurs at composition time rather than through database-engine checks scattered through monitoring logic.

## Backend selection

Default local operation remains SQLite. PostgreSQL is an explicit opt-in through:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

PostgreSQL requires its versioned schema to be current before Search monitoring starts. Schema changes are never triggered by a Search monitoring command. Use:

```powershell
rasai platform database status
rasai platform database migrate
```

There is no silent PostgreSQL-to-SQLite fallback.

## Raw evidence

Raw Search provider evidence is written under:

```text
audits/.rasai/search-monitoring/artifacts/serp/
```

Run manifests are written under:

```text
audits/.rasai/search-monitoring/runs/
```

Evidence payloads use the existing Search evidence sanitizer. Provider credentials are not persisted in the control-plane tables, manifests or reports.

For hosted SaaS, immutable evidence/manifests are expected to move to object storage while PostgreSQL retains relational ownership, references and hashes.

## Query registry CLI

The Product Platform hierarchy must exist before registering a query. Use `rasai platform` to index/create the relevant Project, Property and Environment and obtain their stable IDs.

Register a manual query:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro auto" `
  --domain cliente.example `
  --country BR `
  --language pt-BR `
  --device desktop `
  --depth 20
```

List registered queries:

```powershell
rasai search-monitor --audits-root audits query list
```

Enable or disable one query:

```powershell
rasai search-monitor --audits-root audits query enable --query-id <query-id>
rasai search-monitor --audits-root audits query disable --query-id <query-id>
```

Disabling a registered query also disables its linked local schedule when present.

## Manual execution

Execute one registered query:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id>
```

Estimate the bounded request ceilings without calling providers:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id> --dry-run
```

The dry-run separates:

- Search-provider HTTP request ceiling;
- direct public-content HTTP attempt ceiling;
- Competitive AI provider-call ceiling.

Fixture execution is supported for tests and local validation without provider network calls:

```powershell
rasai search-monitor --audits-root audits run `
  --query-id <query-id> `
  --fixture test-serp.json
```

Fixture mode is manual and is not eligible for a recurring live schedule.

## Recurring schedules

Monitoring reuses the Product Platform scheduler. It does not introduce a second scheduler or execute arbitrary shell strings.

Interval example:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro auto" `
  --domain cliente.example `
  --mode live `
  --provider serpapi `
  --interval-minutes 1440
```

Daily example:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro residencial" `
  --domain cliente.example `
  --mode live `
  --provider serpapi `
  --daily-time 07:00
```

The minimum interval accepted by this Search monitoring surface is 60 minutes. This is a product safety bound, not a recommendation to query every hour. Production cadence must account for provider terms, quota, cost, market volatility and the business value of the query.

Execute only due Search-monitor schedules:

```powershell
rasai search-monitor --audits-root audits run-due
```

The current scheduler is still a single-machine execution mechanism. Persisting schedules in PostgreSQL does not by itself make dispatch horizontally safe; durable queue/claim semantics belong to the hosted execution-plane phase.

## Competitive content and Competitive AI

A registered query can enable deterministic competitive analysis and bounded content inspection.

Content acquisition remains explicit:

```text
--compare-content
--max-content-pages N
```

Competitive AI remains explicit and downstream of consolidated deterministic content evidence:

```text
--ai-competitive
--ai-provider openai
--ai-model <model-id>
--ymyl-mode AUTO|ON|OFF
```

BYOK credentials remain environment/runtime inputs. They are not copied into schedules or the monitoring database.

## Change detection

A successful run is compared only with the previous run of the same registered query context.

Current change states include:

- `POSITION_IMPROVED`;
- `POSITION_REGRESSED`;
- `POSITION_UNCHANGED`;
- `ENTERED_OBSERVED_DEPTH`;
- `LEFT_OBSERVED_DEPTH`;
- `DOMAIN_STATUS_CHANGED`;
- `COMPETITOR_AHEAD_ADDED`;
- `COMPETITOR_AHEAD_REMOVED`;
- `CONTENT_SIGNAL_CHANGED`;
- `CONTENT_VOLUME_CHANGED`;
- `STRUCTURED_DATA_CHANGED`;
- `DETERMINISTIC_GAP_ADDED`;
- `DETERMINISTIC_GAP_RESOLVED`;
- `NOT_COMPARABLE`.

`NOT_FOUND_WITHIN_DEPTH` is never converted into position zero, infinite position or a fabricated absolute rank.

A provider or data-mode change makes the adjacent runs non-comparable for numeric rank deltas. RASAi preserves the provenance difference instead of normalizing it silently.

## Causality boundary

A chronological change is an observation, not proof of ranking causality.

Valid interpretation:

```text
The registered query moved from observed position 8 to position 4 between two comparable runs.
A deterministic content gap observed in the previous run was not present in the current run.
```

Invalid interpretation:

```text
The content change caused the four-position improvement.
```

The available evidence does not establish the private causal mechanism of the Search engine.

## Longitudinal HTML

The longitudinal control-plane report is:

```text
audits/platform-report/search-intelligence.html
```

It shows registered-query timelines, latest position/status, provider/data mode, domains ahead, deterministic gaps, Competitive AI state and the changes materialized for the latest run.

This is deliberately separate from the point-in-time audit report:

```text
audits/AUD-*/report/search-intelligence.html
```

The audit report projects immutable evidence belonging to one audit workspace. The platform report projects recurring operational observations from the selected control-plane backend. The longitudinal report must not rewrite historical audit HTML or `audit.db`.

## Relationship to deployment history

`SEARCH-HISTORY-001` remains the contract for comparing Search evidence between explicit audit workspaces or audit pairs selected around a deployment milestone.

`SEARCH-MONITOR-001` serves a different purpose: continuous observations of a registered query independent of whether a new full audit was executed.

The two surfaces can be correlated by time in a future product dashboard, but neither is allowed to convert temporal proximity to a deployment into a ranking-causality claim.

## PostgreSQL boundary

The monitoring storage seam is now concrete:

```text
Search monitoring domain/runtime
        |
SearchMonitoringRepository
        |
        +-- SQLite adapter: local/default
        +-- PostgreSQL adapter: centralized control plane
```

The PostgreSQL adapter uses the same Project/Property/Environment and schedule authority as the rest of Product Platform. It does not replace or mutate immutable audit evidence.

Runtime details are documented in `POSTGRESQL_CONTROL_PLANE.md`; deployment strategy remains in `POSTGRESQL_MIGRATION_STRATEGY.md`.

## Test and CI policy

Automated tests must not consume customer Search or AI credentials and must not crawl public competitor sites.

Fixture-based Search execution remains mandatory for repository parity tests. PostgreSQL-specific persistence tests run against a real PostgreSQL 18 service container.

Required regression properties include:

- Project/Property/Environment scope integrity;
- duplicate query-context rejection;
- exact rank-change semantics;
- observed-depth boundary semantics;
- provider/data-mode comparability protection;
- control-plane persistence on both supported backends;
- raw evidence and run manifest integrity;
- no recurring write into historical `AUD-*/audit.db`;
- report generation;
- preservation of `SARI-001` and `SCORE-GEO-004` contracts.