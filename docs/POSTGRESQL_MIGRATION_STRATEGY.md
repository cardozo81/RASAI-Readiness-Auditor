# PostgreSQL Migration Strategy

Status: PostgreSQL 18 control-plane backend is implemented as an explicit opt-in path and is being validated before merge. SQLite remains the default local backend.

The current scoring contract remains `SCORE-GEO-004`. This strategy changes product persistence architecture only; it does not redefine scoring, `SARI-001`, audit evidence or report methodology.

## Decision

The first RASAi database boundary implemented on PostgreSQL is the **product control plane**.

It includes product and longitudinal state such as:

- Organization / Workspace / Project;
- Property / Environment;
- users, memberships and roles;
- audit catalog and audit scope links;
- milestones and deployment metadata;
- golden baselines;
- page identities;
- schedules and alert rules;
- integration metadata;
- external dataset catalog;
- usage ledger;
- registered Search monitoring queries;
- Search monitoring run summaries.

The transition does **not** move mutable product state into historical `AUD-*/audit.db` files and does not make PostgreSQL a replacement evidence format.

## Current development baseline

The local PostgreSQL development target is PostgreSQL 18 in Docker. The application is database-location agnostic and connects through the control-plane configuration contract; a hosted deployment can therefore replace the local Docker endpoint without changing domain logic.

The existing SQLite control-plane content and generated reports are test data. They do not need to be imported into the first PostgreSQL database.

The current transition is intentionally:

```text
empty PostgreSQL database
        |
explicit versioned migrations
        |
application-created control-plane data
        |
parity / regression validation
```

A generic SQLite-to-PostgreSQL import tool is deferred until a future real installation has authoritative local state worth preserving.

## Authority model

Recommended hosted authority model:

```text
PostgreSQL
  authoritative product/control-plane relational state

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

This separation prevents the SaaS database from becoming a second interpretation of historical audit evidence.

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
              explicit opt-in / hosted target
```

Current backend configuration:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

or:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

When the backend is not configured, SQLite remains the default. `--platform-db` remains a SQLite-only override.

A PostgreSQL selection without a database URL, or a PostgreSQL connection failure, is an error. The runtime never silently falls back to SQLite because that would create split authority.

Search Query Registry and Search monitoring history use the same selected control-plane backend as Product Platform. There is no separate Search authority database.

## Driver and database compatibility layer

The PostgreSQL implementation uses Psycopg 3 as an optional dependency.

The adapter exposes the narrow DB-API behavior already consumed by canonical Product Platform domain methods. This permits domain validation and business semantics to remain shared while database composition and migrations remain backend-specific.

Requirements enforced by the implementation include:

- parameterized SQL;
- explicit write transactions;
- savepoints for nested transaction scopes;
- UTC session timezone;
- UTF8 server encoding;
- password-redacted database identity;
- sanitized database failures that expose diagnostic type/SQLSTATE without exposing credentials or raw SQL.

Connection pooling is intentionally deferred to the hosted API/service layer. A desktop/local CLI does not need a process-wide request pool merely to prove backend parity.

## Schema migrations

PostgreSQL uses ordered, versioned schema migrations recorded in:

```text
platform_schema_migrations
```

Schema mutation is explicit:

```powershell
rasai platform database status
rasai platform database migrate
```

Normal application startup does not create or upgrade PostgreSQL schema. If the database is empty or behind the runtime-supported schema, PostgreSQL operation fails closed and instructs the operator to run the migration command. A schema newer than the running application is also rejected.

Each migration is applied transactionally and migration execution is idempotent.

This makes schema evolution an auditable deployment step rather than a request-time side effect.

## Compatibility-first schema representation

The first PostgreSQL implementation deliberately separates **database-engine migration** from **domain-representation migration**.

Several existing Product Platform values remain represented exactly as the application already expects:

- ISO-8601 operational values remain canonical text where current APIs expose strings;
- structured domain payloads remain canonical JSON text;
- parity-sensitive booleans remain constrained `0/1` integer values.

This prevents a database-engine change from simultaneously changing Python/domain semantics and makes SQLite/PostgreSQL comparison much more direct.

PostgreSQL-native `jsonb`, `boolean` and `timestamptz` can be introduced later through explicit migrations once repository APIs are independent of the legacy representation and dedicated semantic-parity tests exist. The migration audit timestamp already uses `TIMESTAMPTZ`.

Large immutable evidence payloads remain outside the relational control plane regardless of JSON representation.

## Identifiers

Stable opaque IDs remain part of the cross-backend contract.

Do not regenerate identifiers merely because a different database engine is selected, including:

- organization IDs;
- workspace IDs;
- project/property/environment IDs;
- audit IDs;
- milestone IDs;
- schedule IDs;
- registered Search query IDs;
- Search monitoring run IDs;
- other externally referenced control-plane IDs.

This ensures reports, manifests, lifecycle references and future object-storage keys remain stable.

## Foreign keys and uniqueness

Tenant/scope integrity remains enforced both in application validation and PostgreSQL constraints.

Critical relationships include:

- Workspace -> Organization;
- Project -> Workspace;
- Property -> Project;
- Environment -> Property;
- memberships -> valid organization/user and optional workspace/project scope;
- audit scope links -> indexed audit + Property/Environment;
- milestones/schedules -> valid Project/Property/Environment scope;
- Search monitor query -> valid Project/Property/Environment;
- Search monitor run -> registered query.

PostgreSQL-specific tests execute against a real PostgreSQL 18 service container rather than a mocked SQL layer.

## Tenant isolation

The PostgreSQL backend provides relational scope integrity but does not by itself constitute hosted authentication/authorization.

The first hosted release should add:

1. authenticated organization/workspace context at the API boundary;
2. repository/service methods requiring explicit scope where appropriate;
3. database roles with least privilege;
4. optional PostgreSQL Row Level Security as defense in depth after policy behavior has dedicated tests.

Row Level Security must not substitute for explicit authenticated tenant context.

## Scheduler deployment

The current scheduler remains a local/single-process execution mechanism during this database phase. Moving schedule state to PostgreSQL does not by itself make the scheduler horizontally safe.

Hosted model remains:

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

The hosted scheduler phase must add:

- single logical claim of a due occurrence;
- lease/lock semantics;
- idempotency keys;
- bounded retries;
- failed/dead-letter state;
- UTC scheduling state with user/project timezone only for intended wall-clock schedules;
- per-tenant/provider concurrency and rate limits;
- usage accounting.

`FOR UPDATE SKIP LOCKED` is one viable database-driven claiming mechanism, but durable queue design is a later execution-plane decision and is not implied by the current PostgreSQL persistence backend.

## Search provider and AI credentials

BYOK secrets remain outside ordinary database rows.

Hosted deployments should use a secret manager or encrypted credential service and persist only credential references/metadata required for authorization and rotation.

Provider credentials must not appear in:

- Query Registry rows;
- schedules;
- run manifests;
- reports;
- usage records;
- database status output.

## Object storage

Hosted object storage remains the recommended destination for immutable execution payloads:

```text
AUD bundles
raw provider evidence
competitive artifacts
Competitive AI evidence artifacts
Search monitoring manifests
static report sites
```

PostgreSQL stores ownership, references, hashes, lifecycle metadata and relational indexes required to locate these objects.

## No current SQLite data migration requirement

Because current local control-plane data is test-only, the PostgreSQL implementation does not spend complexity on importing it.

This is distinct from the schema migration mechanism: PostgreSQL **schema** migrations are mandatory and implemented, while **data** migration from the current SQLite test database is unnecessary.

If a future production local installation must be promoted to hosted operation, a separate controlled import process can be added. It should then validate IDs, row counts, foreign keys, serialized values and audit hashes before authority cutover.

## Cutover strategy

Do not use uncontrolled dual-write as the normal authority transition.

For the future production cutover, the preferred approach remains:

```text
freeze old control-plane writes
        |
initialize / validate PostgreSQL authority
        |
import authoritative data only if required
        |
validate scope and integrity
        |
switch application authority
        |
retain previous source read-only for rollback evidence
```

For the current development/test state there is no data import step: PostgreSQL starts clean.

## Hosted deployment baseline

Recommended initial SaaS topology:

```text
HTTPS Load Balancer
        |
RASAi Web/API instances
        |
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

For the first SaaS release, managed PostgreSQL is preferred over self-hosting the database. The local Docker container is a development target, not the proposed production database deployment.