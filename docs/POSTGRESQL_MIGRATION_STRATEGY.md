# PostgreSQL Migration Strategy

Status: PostgreSQL 18 control-plane backend is implemented as an explicit opt-in path. SQLite remains the default local backend.

The scoring contract is `SCORE-GEO-004`. This strategy changes product persistence architecture only; it does not redefine scoring, `SARI-001`, audit evidence or report methodology.

## Decision

The PostgreSQL boundary is the **product control plane**.

It includes product and longitudinal state such as:

- Organization / Workspace / Project;
- Property / Environment;
- users, memberships and roles;
- external identity links `(issuer, subject) -> USR-*`;
- audit catalog and audit scope links;
- milestones and deployment metadata;
- golden baselines;
- page identities;
- schedules and alert rules;
- integration metadata;
- external dataset catalog;
- usage ledger and consumption analytics;
- registered Search monitoring queries;
- Search monitoring run summaries;
- durable execution jobs.

Mutable product state is not written into `AUD-*/audit.db`, and PostgreSQL is not an alternative audit-evidence format.

## Development and deployment model

The local PostgreSQL development target is PostgreSQL 18 in Docker. The application is database-location agnostic and connects through the control-plane configuration contract; hosted deployment uses the same repository/domain boundary against a managed PostgreSQL endpoint.

Development SQLite content is not treated as production authority. A clean PostgreSQL database can therefore be initialized as:

```text
empty PostgreSQL database
        |
explicit versioned migrations
        |
application-created control-plane data
        |
parity / regression validation
```

A SQLite-to-PostgreSQL data-import utility is necessary only when an installation contains authoritative data that must be promoted to PostgreSQL.

## Authority model

Hosted authority model:

```text
PostgreSQL
  authoritative product/control-plane relational state
  users, memberships and external identity links

Object Storage
  immutable AUD bundles
  audit.db files
  evidence artifacts
  generated reports
  Search-monitor raw evidence/manifests

Queue / Scheduler
  execution dispatch and retry state

Workers
  stateless or short-lived audit/integration/Search execution
```

`AUD-*/audit.db` remains a self-contained execution-evidence format. In hosted operation it can be stored as an immutable object rather than becoming the central transactional database.

This separation prevents the SaaS database from becoming a second interpretation of audit evidence.

## Adapter architecture

Database selection occurs at the control-plane composition boundary, not inside business logic.

```text
Product/API services
        |
control-plane store / repository contracts
        |
        +-- SQLite
        |     local/default
        |
        +-- PostgreSQL
              explicit centralized/hosted target
```

Backend configuration:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

or:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

When the backend is not configured, SQLite is the default. `--platform-db` is a SQLite-only override.

A PostgreSQL selection without a database URL, or a PostgreSQL connection failure, is an error. The runtime never silently falls back to SQLite because that would create split authority.

Search Query Registry, Search monitoring, scheduling, execution jobs and external identity links use the same selected control-plane backend. Não existe autoridade paralela específica para identidade ou Search.

## Driver and database boundary

The PostgreSQL implementation uses Psycopg 3 as an optional dependency.

The adapter exposes the DB-API behavior consumed by Product Platform repository/domain methods, while database composition and migrations remain backend-specific.

Requirements include:

- parameterized SQL;
- explicit write transactions;
- savepoints for nested transaction scopes;
- UTC session timezone;
- UTF8 server encoding;
- password-redacted database identity;
- sanitized database failures that expose diagnostic type/SQLSTATE without exposing credentials or raw SQL.

Connection pooling belongs to the hosted API/service deployment layer. Local CLI operation does not require a process-wide request pool.

## Schema migrations

PostgreSQL schema mutation is explicit:

```powershell
rasai platform database status
rasai platform database migrate
```

The control plane uses migration tracks for separated concerns:

```text
platform_schema_migrations              core Product Platform
platform_execution_schema_migrations    durable execution queue
platform_identity_schema_migrations     Identity & Access links
```

Normal application startup does not create or upgrade PostgreSQL schema. If a required migration track is behind the runtime-supported version, PostgreSQL operation fails closed and instructs the operator to run migration. A schema newer than the running application is also rejected.

Each migration is applied transactionally and migration execution is idempotent.

## Identity & Access persistence

OIDC passwords/tokens/secrets are not persisted in PostgreSQL.

The relational identity extension stores only the durable mapping required to connect an externally authenticated identity to the authorization model:

```text
external_identity_id
user_id
issuer
subject
email                 optional/informational
created_at
```

`UNIQUE(issuer, subject)` prevents one external identity from resolving to multiple users.

Authorization derives from `users` and `memberships`. A valid OIDC identity without a RASAi link/membership receives no tenant access.

Client secrets, session secrets, access tokens, ID tokens and refresh tokens remain outside these rows.

## Current schema representation

The PostgreSQL implementation separates **database-engine selection** from **domain-representation changes**.

Current application contracts use:

- canonical ISO-8601 text where APIs expose operational timestamps as strings;
- canonical JSON text where repository contracts require serialized structured payloads;
- constrained `0/1` integers in parity-sensitive boolean columns;
- `TIMESTAMPTZ` for migration audit timestamps.

PostgreSQL-native representation changes such as broader use of `jsonb`, `boolean` and `timestamptz` require explicit migrations and semantic-parity tests. They are not implicit side effects of selecting PostgreSQL.

Large immutable evidence payloads remain outside the relational control plane.

## Identifiers

Stable opaque IDs are part of the cross-backend contract.

Do not regenerate identifiers merely because a different database engine is selected, including:

- organization IDs;
- workspace IDs;
- project/property/environment IDs;
- user IDs;
- external identity IDs;
- audit IDs;
- milestone IDs;
- schedule IDs;
- registered Search query IDs;
- Search monitoring run IDs;
- execution job IDs;
- other externally referenced control-plane IDs.

This keeps reports, manifests, lifecycle references and object-storage keys stable.

## Foreign keys and uniqueness

Tenant/scope integrity is enforced both in application validation and PostgreSQL constraints.

Critical relationships include:

- Workspace -> Organization;
- Project -> Workspace;
- Property -> Project;
- Environment -> Property;
- memberships -> valid organization/user and optional workspace/project scope;
- external identities -> valid internal user and unique issuer/subject;
- audit scope links -> indexed audit + Property/Environment;
- milestones/schedules -> valid Project/Property/Environment scope;
- Search monitor query -> valid Project/Property/Environment;
- Search monitor run -> registered query;
- execution jobs -> valid Organization/Project/Property/Environment scope.

PostgreSQL-specific tests execute against a real PostgreSQL 18 service container rather than a mocked SQL layer.

## Tenant isolation and authentication

The PostgreSQL backend provides relational scope integrity but does not substitute for authentication/authorization.

The Web/API includes provider-neutral OIDC/JWT identity resolution:

```text
OIDC issuer + subject
        |
external identity link
        |
USR-* Principal
        |
membership / role
        |
tenant-scoped repository/API access
```

`trusted-header` is available for trusted gateway/local development scenarios. OIDC validation and database integrity are complementary controls.

Defense in depth may add PostgreSQL Row Level Security after policy behavior has dedicated parity tests. RLS must not substitute for explicit authenticated tenant context in the application.

## Scheduler deployment

Persisting schedule state in PostgreSQL does not by itself make scheduling horizontally safe.

Hosted model:

```text
PostgreSQL schedule/query state
        |
Scheduler service
        |
Durable queue
        |
regional/standard workers
        |
result persistence + object evidence
```

Distributed scheduling requires:

- single logical claim of a due occurrence;
- lease/lock semantics;
- idempotency keys;
- bounded retries;
- failed/dead-letter state;
- UTC scheduling state with user/project timezone only for intended wall-clock schedules;
- per-tenant/provider concurrency and rate limits;
- usage accounting.

`FOR UPDATE SKIP LOCKED` is one viable database-driven claiming mechanism, but durable queue design remains an execution-plane decision and is not implied by PostgreSQL persistence alone.

## Search provider, AI and identity credentials

BYOK provider secrets and identity secrets remain outside ordinary database rows.

Hosted deployments should use a secret manager or encrypted credential service and persist only credential references/metadata required for authorization and rotation.

Secrets must not appear in:

- Query Registry rows;
- schedules;
- run manifests;
- reports;
- usage records;
- external identity rows;
- database status output.

## Object storage

Hosted object storage is the destination for immutable execution payloads:

```text
AUD bundles
raw provider evidence
competitive artifacts
Competitive AI evidence artifacts
Search monitoring manifests
static report sites
```

PostgreSQL stores ownership, references, hashes, lifecycle metadata and relational indexes required to locate these objects.

## Data promotion

Schema migration and data promotion are distinct operations.

PostgreSQL **schema** migrations are mandatory for PostgreSQL operation. **Data** import from SQLite is needed only when the SQLite source contains authoritative state that must be preserved.

A controlled promotion process must validate IDs, row counts, foreign keys, serialized values, identity links, tenant scope and audit hashes before authority cutover.

Recommended cutover pattern when authoritative SQLite state exists:

```text
freeze source control-plane writes
        |
initialize / validate PostgreSQL authority
        |
import authoritative data
        |
validate scope, identity and integrity
        |
switch application authority
        |
retain source read-only until rollback window closes
```

During the current pre-publication development state, PostgreSQL may start clean because local data is test/pilot data rather than production authority.

## Hosted deployment topology

Recommended SaaS topology:

```text
HTTPS Load Balancer / Reverse Proxy
        |
RASAi Web/API instances
        |
        +-- OIDC Identity Provider
        +-- managed PostgreSQL
        +-- managed queue
        +-- object storage
        +-- secret manager
        |
worker pool
        +-- audit workers
        +-- Search monitoring workers
        +-- integration workers
```

Operational requirements for hosted PostgreSQL include:

- private network access where supported;
- TLS;
- automated backups;
- point-in-time recovery;
- encryption at rest;
- monitoring of connection saturation, locks, slow queries and storage;
- separate migration/application credentials where practical;
- tested restore procedure;
- controlled migrations during deployments.

Managed PostgreSQL is preferred over self-hosting the production database. The local Docker container is a development target.
