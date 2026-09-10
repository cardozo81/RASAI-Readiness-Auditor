# PostgreSQL Control Plane

Status: PostgreSQL 18 backend implemented behind explicit configuration. SQLite is the default local control-plane backend.

This capability changes product persistence only. It does not alter `SARI-001`, `SCORE-GEO-004`, audit collection, scoring arithmetic or immutable `AUD-*/audit.db` evidence.

## Storage boundary

```text
Product/control-plane relational state
  SQLite      local/default
  PostgreSQL  centralized/hosted target

Immutable audit evidence
  AUD-*/audit.db
  reports
  artifacts
  provider evidence
```

PostgreSQL is the centralized relational authority for product/control-plane state when selected. `AUD-*/audit.db` remains the immutable execution-evidence format and is not replaced by PostgreSQL.

## Installation

PostgreSQL support is optional so a normal local installation does not acquire a database-driver dependency it does not use.

```powershell
python -m pip install -e ".[postgresql]"
```

The adapter uses Psycopg 3. Application code is not coupled to Docker or to a specific cloud provider.

## Backend selection

SQLite:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

When the backend variable is absent, SQLite is selected and the local control-plane database is:

```text
audits/.rasai/platform.db
```

PostgreSQL:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
```

`postgres` and `pg` are accepted backend-name aliases, while `postgresql` is the documented value.

`--platform-db` is SQLite-only. A configured PostgreSQL backend requires `RASAI_PLATFORM_DATABASE_URL` and never falls back silently to SQLite. This prevents split authority.

The database password is not emitted by backend status output. Display URLs are redacted to retain user/host/database while removing password and sensitive connection parameters.

## Connection targets

The PostgreSQL adapter is endpoint-neutral. The same runtime can connect to:

- a local PostgreSQL 18 Docker container for development;
- a PostgreSQL server on another machine;
- a managed PostgreSQL service;
- a hosting provider that exposes a standards-compatible PostgreSQL TCP endpoint.

Local development example:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@127.0.0.1:5432/rasai_control_plane
```

Hosted example:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@db.example-host.net:5432/rasai_control_plane?sslmode=require&connect_timeout=10&application_name=rasai
```

Provider-specific pooler endpoints are acceptable when they expose a PostgreSQL-compatible connection contract.

For remote/hosted databases:

- TLS should be enabled; `sslmode=require` is the minimum practical profile and `sslmode=verify-full` is preferred when hostname/CA verification is available;
- inbound connectivity must be allowed from the RASAi execution environment;
- the database user must have permissions required by explicit schema migrations;
- credentials remain runtime secrets and must not be committed;
- special characters in URL credentials must be percent-encoded.

RASAi does not detect Docker versus hosting and does not branch behavior by provider. Database location is represented by the connection URL and network/TLS configuration.

If PostgreSQL is explicitly selected and unavailable, the control plane fails closed. Returning to SQLite requires an explicit backend selection.

## Schema migrations

PostgreSQL schema mutation is explicit. Normal application startup and Search monitoring do not create or upgrade schema.

Inspect schema state:

```powershell
rasai platform database status
```

Apply pending migrations:

```powershell
rasai platform database migrate
```

Application startup requires the database schema to match the runtime-supported version. Empty, behind or newer-than-supported schema state is rejected with an explicit diagnostic.

Migrations are ordered, transactional and recorded in migration tables. Re-running migration against a current schema is idempotent.

## Current PostgreSQL scope

The PostgreSQL control plane covers the product-domain entities required by the current architecture, including:

- organizations, users, memberships and workspaces;
- projects, properties and environments;
- audit catalog and audit scope links;
- milestones and golden baselines;
- page identities;
- comparisons;
- schedules, alert rules and notifications;
- integration metadata;
- external dataset catalog/records;
- usage events and consumption analytics;
- Search monitoring query registry and run summaries;
- durable execution jobs;
- external identity links for OIDC/JWT identity resolution.

Search monitoring, scheduling, usage accounting, identity and execution jobs use the same selected control-plane authority.

## Current relational representation

The PostgreSQL schema preserves the domain representation expected by the current application contracts:

- operational ISO-8601 values use canonical text where APIs expose strings;
- structured domain payloads use canonical JSON text where required by repository contracts;
- parity-sensitive booleans use constrained `0/1` values where that is the current schema contract;
- migration audit timestamps use `TIMESTAMPTZ`.

Representation changes such as broader adoption of `jsonb`, PostgreSQL `boolean` or `timestamptz` require explicit schema migrations and parity validation. They are not coupled implicitly to backend selection.

PostgreSQL uses UTF8 and the RASAi session timezone is UTC.

## Transaction behavior

The PostgreSQL adapter uses parameterized statements only.

- normal read operations use autocommit so read-only traffic does not remain in idle transactions;
- domain writes use explicit transactions;
- nested transaction scopes use savepoints;
- failures roll back the affected transaction;
- database errors exposed to CLI/runtime are sanitized and may include exception type/SQLSTATE, never password, raw connection URL or raw SQL statement.

## Local development and hosted operation

A local PostgreSQL 18 Docker container is appropriate for development and parity testing. The application connects through the same `RASAI_PLATFORM_DATABASE_URL` contract used by a hosted deployment.

For SaaS operation, managed PostgreSQL is the recommended production target. Provider selection remains a deployment decision; the repository contract is cloud-neutral.

## Development/test data

Local SQLite control-plane content created during development is not treated as production authority. A clean PostgreSQL database may therefore be initialized through explicit schema migrations and populated through normal application contracts.

A SQLite-to-PostgreSQL data import utility is required only when an installation contains authoritative data that must be promoted. Such a process must validate identifiers, foreign keys, row counts, hashes and tenant scope before cutover.

## CI contract

PostgreSQL support is validated against PostgreSQL 18 in GitHub Actions. The integration suite verifies at least:

- schema migration and idempotence;
- UTF8/UTC contract;
- hierarchy and tenant-scope behavior;
- schedules, usage and execution-job persistence;
- transaction rollback;
- Query Registry and Search monitoring history;
- local and hosted/TLS connection profiles;
- no mutation of `AUD-*/audit.db` by recurring Search monitoring;
- explicit backend selection and absence of silent fallback;
- credential redaction.

SQLite regressions remain in the normal Product Platform regression suites. A portable safety gate runs without Psycopg/PostgreSQL so centralized support cannot become a hidden dependency of local SQLite operation.

## SaaS boundary

PostgreSQL is the control-plane database foundation. A complete hosted SaaS deployment additionally requires authenticated tenant context, Web/API services, durable queue/scheduler claim semantics, object storage, secret management and stateless/short-lived workers.

Persisting schedules in PostgreSQL does not by itself make a multi-replica scheduler horizontally safe; distributed execution requires atomic claims, leases/locks, idempotency, bounded retries and tenant/provider concurrency controls.
