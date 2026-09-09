# PostgreSQL Migration Strategy

Status: architecture decision defined; PostgreSQL adapter not enabled in the current local runtime.

The current scoring contract remains `SCORE-GEO-004`. This strategy changes product persistence architecture only; it does not redefine scoring, `SARI-001`, audit evidence or report methodology.

## Decision

The first RASAi database boundary to migrate to PostgreSQL is the **product control plane**.

The migration target includes product and longitudinal state such as:

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

The migration target does **not** mean copying mutable application behavior into historical `AUD-*/audit.db` files.

## Authority after SaaS migration

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

`AUD-*/audit.db` remains a self-contained execution-evidence format. In hosted operation it can be stored as an immutable object instead of becoming the central transactional database.

This separation prevents the SaaS database from becoming a second interpretation of historical audit evidence.

## Why PostgreSQL is not activated in the Search monitoring implementation

The current Windows/local product is still a single-machine runtime. SQLite remains technically appropriate for that operating mode and provides simple installation, portable local state and offline operation.

Activating PostgreSQL in the same change as Query Registry and recurring Search monitoring would combine two independent risks:

1. a new longitudinal product domain;
2. a new production database engine and deployment dependency.

The safer sequence is:

```text
stabilize domain contracts on local control plane
        |
validate Query Registry / schedules / monitoring history
        |
freeze repository-level behavior and migration invariants
        |
implement PostgreSQL adapter in a dedicated change
        |
validate parity and migration tooling
        |
introduce hosted API/control-plane authority
```

The monitoring implementation therefore introduces a repository boundary now and leaves PostgreSQL activation to the dedicated persistence phase.

## Trigger for starting PostgreSQL implementation

The PostgreSQL implementation phase should begin when all of the following are true:

- Organization / Workspace / Project / Property / Environment contracts are stable;
- multi-property audit indexing is stable;
- schedules and lifecycle metadata have stable semantics;
- Search Query Registry and longitudinal run semantics have passed regression validation;
- no historical audit evidence needs to be rewritten to support these product functions;
- the next product milestone requires concurrent users, remote workers or centralized state.

With recurring Search monitoring implemented, the data model is sufficiently concrete to design the adapter. The recommended next persistence phase is therefore **after monitoring is validated and merged**, before the hosted web/API plane becomes the primary product interface.

## Adapter architecture

Database selection must occur at the control-plane composition boundary, not inside business logic.

Target shape:

```text
Product/API services
        |
Domain repositories / store contracts
        |
        +-- SQLite implementation
        |      local Windows/CLI
        |
        +-- PostgreSQL implementation
               hosted SaaS
```

The application must not scatter checks such as `if postgres` across scheduling, Search monitoring, deployment comparison or tenancy logic.

The current `SearchMonitoringRepository` is the first explicit repository contract for the new longitudinal Search domain. The broader Product Platform should be refactored toward the same pattern before PostgreSQL becomes authoritative.

## Proposed PostgreSQL implementation

### Driver and pooling

Use a maintained PostgreSQL driver with explicit transaction support and a connection pool suitable for the hosted API/runtime.

The adapter must support:

- parameterized SQL only;
- transaction boundaries owned by repository/service operations;
- TLS in hosted environments;
- bounded pool size;
- statement/connection timeout policy;
- health/readiness checks;
- database errors mapped to domain-level failures where appropriate.

The exact Python driver should be selected in the dedicated implementation branch after compatibility with the supported Python/runtime matrix is verified.

### Schema migrations

Hosted PostgreSQL must use ordered, versioned schema migrations. Automatic table creation at request time is not an acceptable production migration mechanism.

A migration framework such as Alembic is appropriate if the implementation adopts SQLAlchemy metadata; otherwise a small explicit migration runner can be used. The key requirement is deterministic forward migration with an auditable schema version history.

Do not silently infer schema changes from application startup.

### Identifiers

Existing stable opaque IDs must be preserved during migration.

Do not regenerate:

- organization IDs;
- workspace IDs;
- project/property/environment IDs;
- audit IDs;
- milestone IDs;
- schedule IDs;
- registered Search query IDs;
- other externally referenced control-plane IDs.

ID stability is required so historical reports, manifests and audit catalog references remain valid.

### Time values

PostgreSQL should use timezone-aware timestamps for operational time columns. Migration tooling must normalize existing ISO-8601 SQLite text timestamps without changing the represented instant.

Application APIs should continue to use explicit timezone-aware values.

### JSON values

Fields currently persisted as canonical JSON text can become PostgreSQL `jsonb` where the field is structurally queried or benefits from validation/indexing.

Do not convert every JSON artifact into relational columns. Large immutable evidence payloads belong in object storage with references/hashes in PostgreSQL.

### Boolean values

SQLite integer booleans should become PostgreSQL boolean columns. Migration validation must prove semantic equivalence rather than relying on implicit casting.

### Foreign keys and uniqueness

All current tenant/scope foreign-key and uniqueness rules must remain enforced in PostgreSQL. Database-level integrity is complementary to application-level validation.

Critical relationships include:

- Workspace -> Organization;
- Project -> Workspace;
- Property -> Project;
- Environment -> Property;
- audit scope links -> indexed audit + Property/Environment;
- milestones/schedules -> valid Project/Property/Environment scope;
- Search monitor query -> valid Project/Property/Environment;
- Search monitor run -> registered query.

## Tenant isolation

The first hosted release should enforce tenant scope in service/repository queries and authorization logic.

PostgreSQL Row Level Security can be considered as an additional defense-in-depth layer, but it must not be used as a substitute for explicit authenticated tenant context in application services.

Recommended sequence:

1. authenticated organization/workspace context at the API boundary;
2. repository methods requiring explicit scope where appropriate;
3. database roles with least privilege;
4. optional Row Level Security after policy behavior has dedicated tests.

## Scheduler deployment

The current local scheduler remains valid for Windows/local execution. Hosted SaaS should not rely on one long-running desktop process polling a SQLite file.

Hosted model:

```text
PostgreSQL schedule/query state
        |
Scheduler service
        |
Durable queue
        |
Regional/standard workers
        |
Result persistence + object evidence
```

Scheduler requirements:

- single logical claim of a due job;
- lease/lock semantics so multiple scheduler replicas do not double-dispatch;
- idempotency key for one scheduled occurrence;
- bounded retry policy;
- explicit failed/dead-letter state;
- UTC storage with user/project timezone used only to calculate intended local schedules;
- concurrency/rate limits per tenant/provider;
- usage accounting per execution.

PostgreSQL row locking with `FOR UPDATE SKIP LOCKED` is a viable mechanism for claiming due work if the scheduler remains database-driven. A managed queue can then carry execution jobs to workers.

## Search provider and AI keys

BYOK secrets must not be migrated from environment variables into ordinary database columns.

Hosted deployments should use a secret manager or encrypted credential service and persist only a credential reference/metadata necessary for authorization and rotation.

The database must never expose provider keys in:

- query registry rows;
- schedules;
- run manifests;
- reports;
- usage records.

## Object storage

Hosted object storage is the recommended home for immutable execution payloads:

```text
AUD bundles
raw provider evidence
competitive artifacts
Competitive AI evidence artifacts
Search monitoring manifests
static report sites
```

PostgreSQL stores references, hashes, ownership, lifecycle metadata and indexes needed to locate those objects.

Objects should use immutable/versioned keys or a write-once policy for evidence whose SHA-256 is already cataloged.

## Migration tooling from SQLite

The migration must be a deliberate command/process, not an implicit side effect of connecting to PostgreSQL.

Recommended migration stages:

1. open local `platform.db` read-only for export;
2. verify supported schema versions;
3. export rows in dependency order;
4. import into a new PostgreSQL tenant/control-plane database;
5. preserve all stable IDs;
6. convert timestamps, booleans and JSON deterministically;
7. validate row counts for every table;
8. validate all foreign keys and unique constraints;
9. verify audit catalog SHA-256 values are unchanged;
10. verify schedules retain enabled/disabled state and next/last-run metadata;
11. verify Search monitoring query/run counts and chronology;
12. generate a migration manifest with source hash, target schema version and validation results;
13. switch authority only after all validation gates pass.

The source SQLite file should remain available as rollback evidence until the hosted cutover is accepted.

## Cutover strategy

Do not make uncontrolled dual-write the normal migration strategy. Dual writes create ambiguity about which database is authoritative and require distributed consistency handling.

Preferred cutover:

```text
maintenance/freeze window for control-plane writes
        |
final SQLite export
        |
validated PostgreSQL import
        |
application authority switch
        |
read-only retention of source SQLite snapshot
```

For larger future installations where a freeze window is unacceptable, change-data-capture or an explicit dual-write migration layer can be designed as a separate operational project. It should not be introduced preemptively into the current local product.

## Configuration contract for the future adapter

A future implementation should use one explicit control-plane database configuration contract. A suitable shape is:

```text
RASAI_PLATFORM_DATABASE_URL
```

Examples conceptually include a local SQLite URL/path or PostgreSQL DSN. The variable should not be exposed as supported production configuration until the PostgreSQL adapter and migration validation exist.

There must be no silent fallback from a configured PostgreSQL authority to local SQLite when the hosted database is unavailable. Such fallback would split authoritative state.

Local Windows mode may continue to default explicitly to:

```text
audits/.rasai/platform.db
```

## Hosted deployment baseline

Recommended initial hosted topology:

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

Operational requirements for PostgreSQL:

- private network access where supported;
- TLS;
- automated backups;
- point-in-time recovery;
- encryption at rest;
- monitoring of connection saturation, locks, slow queries and storage;
- separate migration/application credentials;
- tested restore procedure;
- defined retention policy;
- controlled schema migration during deployments.

For the first SaaS release, a managed PostgreSQL service is preferred over self-hosting the database.

## Regional execution and future hubs

The previously discussed orchestrator/hub model remains compatible with this boundary.

```text
Central control plane / PostgreSQL
        |
Scheduler + queue
        |
        +-- worker/hub region A
        +-- worker/hub region B
        +-- worker/hub region C
        |
central result metadata + object evidence
```

Regional hubs should be execution nodes, not independent authoritative databases. They may use short-lived local caches/spools for resilience, but canonical tenant/query/schedule/run state returns to the central control plane.

This avoids the operational cost of keeping multiple regional relational databases mutually consistent.

## Acceptance criteria before PostgreSQL becomes authoritative

The PostgreSQL phase is not complete until automated validation demonstrates:

- domain repository parity between SQLite and PostgreSQL for supported operations;
- tenant/scope integrity parity;
- schedule semantics parity;
- Search Query Registry parity;
- monitoring-history ordering and change semantics parity;
- audit index hash preservation;
- migrations are repeatable against a clean database;
- migration failure does not partially switch authority;
- backup/restore is tested;
- Windows/local SQLite mode still works;
- Linux hosted runtime works;
- `SARI-001` and `SCORE-GEO-004` remain unchanged;
- public reports and documentation remain methodologically consistent.

## Implementation sequence after Search monitoring

Recommended dedicated persistence workstream:

```text
1. Inventory Product Platform store methods and callers
2. Define repository/service interfaces for control-plane domains
3. Move SQLite-specific SQL behind SQLite adapters
4. Add PostgreSQL schema migrations
5. Implement PostgreSQL adapters
6. Add SQLite/PostgreSQL behavioral contract tests
7. Implement validated SQLite -> PostgreSQL migration command
8. Add object-storage evidence abstraction
9. Add hosted scheduler claim/queue semantics
10. Deploy a staging control plane on managed PostgreSQL
11. Execute migration and restore drills
12. Enable hosted authority only after parity gates pass
```

This is the recommended moment and method for PostgreSQL: **after the recurring-monitoring contracts are validated, and before the web SaaS becomes the primary authoritative control plane**.
