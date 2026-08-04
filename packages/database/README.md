# Database package (EPSILON-01)

This package defines the normalized PostgreSQL persistence model for the
Collaboration Operations Platform and its migration-first upgrade contract.

## Migration discipline

- Migrations are strictly numbered and ordered:
  - `0001-foundation.sql`
  - `0002-domain-core.sql`
  - `0003-operability.sql`
  - `0004-roles-and-privileges.sql`
- Each migration is append-only and is intended to be applied in order.
- `MIGRATIONS` in `src/schema.ts` records the contract used by later packets.

## EPSILON-02 repository and unit-of-work primitives

- Repositories are represented by `PartitionRepository`, `PrincipalRepository`,
  `TaskRepository`, `DecisionRepository`, `OutboxRepository`, and `AuditRepository`
  in `src/epsilon-02.ts`.
- `RepositoryStore` provides an atomic mutation execution surface:
  - command envelope + idempotency key
  - command receipt generation
  - duplicate replay returning prior receipt when payload matches
  - exact payload mismatch rejection with `IdempotentConflictError`
  - atomic commit semantics for in-memory writes, outbox staging, and audit
    staging within one unit of work
- The in-memory store is intentionally lightweight and packet-local so later packets
  can replace it with a concrete PostgreSQL adapter behind the same contract.

## Canonical entities

- Partition-aware, canonical aggregates:
  `person`, `organization`, `relationship`, `engagement`, `project`, `matter`,
  `interaction`, `meeting`, `note`, `artifact`, `decision`, `commitment`,
  `task`, `milestone`, `risk`.
- Source and work envelopes:
  `source`, `source_cursor`, `source_envelope`, `import_run`,
  `normalization_receipt`, `outbox_event`, `job`.
- Governance and custody:
  `principal`, `membership`, `capability_grant`, `policy_decision`,
  `audit_event`, `retention_rule`, `legal_hold`, `export_bundle`,
  `restore_receipt`.
- Operational projections:
  `search_document`, `search_sync_receipt`, `saved_view`, `notification`,
  `automation_rule`, `automation_run`.

## Role set (0004 migration)

- `cop_owner`
- `cop_migrator`
- `cop_runtime`
- `cop_worker`
- `cop_readonly`

## Bootstrap behavior

- `CREATE_TABLES_SQL` includes the table bootstrap subset (`0001`–`0003`) without
  role DDL so package-local initialization does not require superuser rights.
- Role and grant DDL are isolated in `0004-roles-and-privileges.sql`.
- `DatabaseClient.initSchema()` uses the bootstrap SQL for local development
  database initialization.

## EPSILON-03 durable jobs, leases, retries, and synthetic seed lifecycle

- `JobRepository` supports:
  - enqueueing jobs with idempotency keys and retry envelopes;
  - deterministic claim/heartbeat/recover semantics with bounded lease windows;
  - completion, retryable/non-retryable failure, and interruption recovery paths;
  - deterministic backoff for retries and dead-letter transitions.
- `SyntheticSeedRepository` supports:
  - seed creation for synthetic partitions only;
  - custody-hash guarded reset paths and state transitions;
  - seed lifecycle (`active`, `resetting`, `sealed`) with reset-count/version tracking.
- `RepositoryStore` snapshot now includes jobs and synthetic seeds so job/seed
  mutations remain atomic with other in-memory domain aggregates during a unit-of-work.
