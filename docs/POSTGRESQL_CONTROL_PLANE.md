# PostgreSQL Control Plane

Status: PostgreSQL 18 backend implemented behind an explicit opt-in configuration. SQLite remains the default local control-plane backend.

This capability changes product persistence only. It does not alter `SARI-001`, `SCORE-GEO-004`, audit collection, scoring arithmetic or immutable `AUD-*/audit.db` evidence.

## Storage boundary

The RASAi persistence boundary is:

```text
Product/control-plane relational state
  SQLite      local/default
  PostgreSQL  explicit opt-in / hosted target

Immutable audit evidence
  AUD-*/audit.db
  reports
  artifacts
  provider evidence
```

PostgreSQL is not a replacement format for historical `audit.db` evidence. The control plane stores catalog, scope, lifecycle and longitudinal product state; audit evidence remains independently verifiable.

## Installation

PostgreSQL support is optional so a normal Windows/local installation does not acquire a database-driver dependency it does not use.

```powershell
python -m pip install -e ".[postgresql]"
```

The adapter uses Psycopg 3. Application code does not depend on a specific Docker or cloud provider.

## Backend selection

Default behavior is unchanged:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

When `RASAI_PLATFORM_DB_BACKEND` is absent, SQLite is selected and the canonical local database remains:

```text
audits/.rasai/platform.db
```

PostgreSQL is explicit:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
```

`postgres` and `pg` are accepted as backend-name aliases, but the documented value is `postgresql`.

`--platform-db` is SQLite-only. A configured PostgreSQL backend requires `RASAI_PLATFORM_DATABASE_URL` and never falls back to SQLite if the URL is absent or the server is unavailable. This prevents split authority.

The database password is not emitted by backend status output. Display URLs are redacted to retain user/host/database while removing the password and connection query parameters.

## Connection targets: Docker or hosted PostgreSQL

The PostgreSQL adapter is endpoint-neutral. The same runtime can connect to a local Docker container, a PostgreSQL server on another machine, a managed database service or a hosting provider that exposes a standards-compatible PostgreSQL TCP endpoint.

Local Docker development example:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@127.0.0.1:5432/rasai_control_plane
```

Hosted/remote example:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@db.example-host.net:5432/rasai_control_plane?sslmode=require&connect_timeout=10&application_name=rasai
```

A provider-specific pooler endpoint on another port is also acceptable when it presents a PostgreSQL-compatible connection contract, for example port `6543`.

Connection query parameters are preserved and passed to Psycopg/libpq. This allows provider-required options such as `sslmode`, `connect_timeout`, `application_name` and certificate parameters without adding provider-specific logic to RASAi.

For remote or hosted databases:

- TLS should be enabled; `sslmode=require` is the minimum practical remote profile, while `sslmode=verify-full` is preferred when the provider exposes a trusted CA and hostname verification;
- the provider must permit inbound PostgreSQL connectivity from the RASAi execution environment, including IP allowlisting/firewall rules when applicable;
- the database/user must have the permissions required by the explicit RASAi schema migrations;
- credentials remain runtime secrets and must not be committed to Git;
- special characters in URL usernames/passwords must be percent-encoded;
- a generic web-hosting plan that does not expose remote PostgreSQL TCP access cannot be used as a RASAi control-plane endpoint merely because it offers PostgreSQL internally to hosted applications.

RASAi does not detect Docker versus hosting and does not branch behavior by provider. Database location is an operational concern represented solely by the connection URL and network/TLS configuration.

If a hosted PostgreSQL endpoint is unavailable while PostgreSQL is explicitly selected, RASAi fails closed. The operator may explicitly select `sqlite` to return to portable local operation; there is no automatic PostgreSQL-to-SQLite fallback.

## Schema migrations

PostgreSQL schema mutation is an explicit operation. Normal application startup and Search monitoring do not create or upgrade schema.

Inspect schema state:

```powershell
rasai platform database status
```

Apply pending migrations:

```powershell
rasai platform database migrate
```

Application startup requires the database schema to match the runtime-supported version. If the database is empty or behind, startup fails with an instruction to run the migration command. A database newer than the running RASAi build is also rejected.

Migrations are ordered and recorded in:

```text
platform_schema_migrations
```

Each migration is applied in its own transaction. Re-running the migration command when the schema is current is idempotent.

## Current PostgreSQL schema scope

The PostgreSQL control plane covers the product-domain entities already authoritative in the local control plane, including:

- organizations, users, memberships and workspaces;
- projects, properties and environments;
- audit catalog and audit scope links;
- milestones and golden baselines;
- page identities;
- comparisons;
- schedules, alert rules and notifications;
- integration metadata;
- external dataset catalog/records;
- usage events;
- Search monitoring query registry;
- Search monitoring run summaries.

Search monitoring uses the same control-plane database as Product Platform. It does not open a second PostgreSQL database for Search state.

## Compatibility-first representation

The first PostgreSQL schema intentionally preserves several existing application serialization contracts:

- operational ISO-8601 values remain canonical text where Product Platform currently treats them as strings;
- JSON domain payloads remain canonical JSON text;
- application booleans remain constrained `0/1` integer values in parity-sensitive tables.

This is deliberate. The first database-engine transition proves behavioral parity without simultaneously changing the application data model.

PostgreSQL-native `jsonb`, `boolean` and `timestamptz` conversions can be introduced later as explicit versioned migrations after repository APIs stop depending on the legacy serialized representation. The migration-history timestamp itself already uses `TIMESTAMPTZ`.

This compatibility choice does not change the server requirements: PostgreSQL uses UTF8 and the RASAi session timezone is UTC.

## Transaction behavior

The PostgreSQL adapter uses parameterized statements only. Existing control-plane domain methods reuse their established transaction boundaries through a narrow DB-API compatibility layer.

Normal read operations use an autocommit connection so read-only traffic does not remain in idle transactions. Domain write blocks explicitly open transactions and commit or roll back as a unit. Nested transaction blocks use savepoints.

Database errors exposed to the CLI/runtime are sanitized. They may include the exception type and SQLSTATE for diagnosis, but not the connection URL, password or raw SQL statement.

## Local development and hosted operation

A local PostgreSQL 18 Docker container is appropriate for development and parity testing. The application connects through the same `RASAI_PLATFORM_DATABASE_URL` contract that a hosted deployment will use.

The hosted SaaS target should use managed PostgreSQL rather than treating a developer Docker container as production infrastructure. Provider selection remains an operational deployment decision; the application repository contract does not depend on AWS, Azure, Google Cloud or a specialized PostgreSQL provider.

## Existing SQLite test data

The current SQLite control-plane content and historical reports are development/test data and do not need to be imported into the first PostgreSQL control plane.

The recommended current transition is therefore:

```text
new PostgreSQL database
  -> explicit schema migration
  -> empty canonical control plane
  -> controlled test/real data created through application contracts
```

A generic SQLite-to-PostgreSQL import utility is not a prerequisite for this implementation. Such a tool should be introduced only if a future real local installation needs to preserve authoritative control-plane state during promotion to hosted operation.

## CI contract

PostgreSQL support is validated against a real PostgreSQL 18 service container in GitHub Actions. The integration suite verifies at least:

- schema migration and idempotence;
- UTF8/UTC server contract;
- hierarchy and tenant-scope domain behavior;
- schedules and usage persistence;
- transaction rollback;
- Query Registry and Search monitoring run history;
- local-Docker and hosted/TLS connection URL profiles;
- no creation or mutation of `AUD-*/audit.db` by recurring Search monitoring;
- explicit backend selection and lack of silent fallback;
- credential redaction.

SQLite regressions remain part of the normal full Product Platform and repository regression suites. A separate portable safety gate runs without Psycopg or a PostgreSQL service so PostgreSQL support cannot become a hidden dependency of the local SQLite runtime.

## Production boundary not implemented here

The PostgreSQL control-plane backend does not by itself implement the full hosted SaaS runtime. Later phases still include authenticated tenant context, hosted API/services, durable queue/scheduler claim semantics, object storage, secret management and stateless workers.

Until that hosted execution plane exists, the current local scheduler remains a single-machine execution mechanism even when PostgreSQL persistence is being tested.