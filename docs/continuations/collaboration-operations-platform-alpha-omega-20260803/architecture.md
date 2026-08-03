# Collaboration Operations Platform architecture

## Product thesis

This is the owner's private collaboration operating system: capture once, preserve provenance,
retrieve across time, and operate commitments without allowing one relationship to see another.
It is not a generic CRM, a shared drive, or another client project. Those systems remain sources;
this platform is the private control plane that relates their records.

The first user is the owner. Collaborator-facing access is a later, scoped projection over the same
partition model. No self-service signup, ambient organization membership, or cross-partition search
exists. A record without a partition is invalid.

## Non-negotiable invariants

1. Every durable object carries `partition_id`, provenance, classification, creator, timestamps,
   and an immutable public-safe identifier.
2. Authorization is default-deny in application policy and PostgreSQL row-level security.
3. The database owner is never the application runtime role; runtime tests force row security.
4. Raw source envelopes are append-only. Normalized records may evolve through versioned commands,
   never by erasing provenance.
5. Cross-partition links store only approved references; they never grant visibility transitively.
6. Secrets and raw private payloads never enter Git, logs, traces, fixtures, prompts, or receipts.
7. Synthetic fixtures exercise every workflow before any live source is connected.
8. Deletion is recoverable by default. Physical purge requires a retention/custody predicate and a
   separately authorized receipt.
9. Search results, automations, exports, and agent tools pass through the same policy engine as the
   primary API.
10. Every external side effect is idempotent, attributable, replay-safe, and represented by a
    durable receipt.

## Chosen suite shape

The repository is a private TypeScript monorepo using strict compilation and a pinned lockfile. The
implementation discovers current supported package versions at genesis rather than encoding future
version names in this plan.

### Applications

| Surface | Responsibility | Boundary |
|---|---|---|
| `apps/web` | Next.js App Router owner console and scoped collaborator portal | Browser-facing; no direct database access |
| `apps/api` | Fastify JSON-Schema API, OpenAPI document, authn/authz enforcement | Sole synchronous command/query boundary |
| `apps/worker` | Ingest, indexing, automation, export, notification, and maintenance jobs | Claims durable jobs; idempotency required |
| `apps/cli` | Owner administration, import/export, diagnostics, backup/restore, fixture tooling | Local/operator surface; same application services |
| `apps/mcp` | Scoped Model Context Protocol tools/resources for agents | No authority broader than bearer and partition |

Next.js remains deployable as a normal Node.js process or container, while Fastify's schema-first
validation keeps request and response disclosure explicit. These choices are grounded in the
current official [Next.js deployment](https://nextjs.org/docs/app/getting-started/deploying),
[Fastify validation](https://fastify.dev/docs/latest/Reference/Validation-and-Serialization/), and
[MCP TypeScript SDK](https://modelcontextprotocol.io/docs/sdk) contracts.

### Packages

| Package | Owns |
|---|---|
| `packages/contracts` | JSON Schemas, generated TypeScript types, OpenAPI/event schemas, compatibility checks |
| `packages/domain` | Entities, value objects, commands, events, invariants; no framework imports |
| `packages/policy` | Partition scopes, roles, capabilities, field redaction, policy decision receipts |
| `packages/database` | Numbered SQL migrations, query repositories, transaction/outbox primitives |
| `packages/object-store` | Content-addressed encrypted blobs, metadata, quarantine, retention adapters |
| `packages/ingest` | Source envelopes, parsers, normalization, dedupe, provenance, dead-letter handling |
| `packages/search` | PostgreSQL full-text indexing, ranking, filters, highlights, optional embedding adapter |
| `packages/workflows` | Commitments, tasks, decisions, meetings, reviews, reminders, state machines |
| `packages/connectors` | Connector SDK, capability manifests, cursors, rate limits, synthetic adapters |
| `packages/automation` | Triggers, rules, approvals, job orchestration, run receipts, replay controls |
| `packages/audit` | Append-only audit events, integrity chains, redacted operational views |
| `packages/observability` | Structured logs, metrics, traces, correlation and redaction conventions |
| `packages/ui` | Accessible design tokens, components, interaction patterns, empty/error/loading states |
| `packages/testkit` | Deterministic factories, synthetic personas, policy matrices, fake clocks/services |
| `packages/config` | Typed configuration schema and environment capability discovery |

### Infrastructure

- PostgreSQL is canonical structured state. Numbered SQL migrations are reviewable artifacts.
- PostgreSQL full-text search is the deterministic baseline; embeddings are optional, additive,
  provider-neutral, and never required for exact retrieval. PostgreSQL documents both
  [row-level security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) and
  [full-text search](https://www.postgresql.org/docs/current/textsearch.html) as native features.
- S3-compatible object storage holds encrypted, content-addressed attachments. A filesystem adapter
  supports hermetic local tests; no vendor is hard-coded into domain code.
- A transactional outbox and durable jobs table coordinate API and worker processes before any
  external queue is introduced. An external queue is justified only by measured pressure.
- OpenTelemetry-compatible instrumentation is emitted through an adapter, with private fields
  excluded before export.
- Local multi-process development uses Docker Compose because web, API, worker, PostgreSQL, and
  object storage form a coordinated system. Individual package tests remain native and hermetic.

## Canonical domain

### Boundary and identity

- `Principal`: owner, service, agent, or invited collaborator identity.
- `Partition`: the non-transitive security and records boundary for one collaboration/client.
- `Membership`: principal-to-partition role with explicit start, end, grantor, and receipt.
- `CapabilityGrant`: narrowly scoped action grant, never inferred from a cross-record link.
- `PolicyDecision`: allow/deny, reason code, policy version, actor, resource, request correlation.

### Relationship and work

- `Person`, `Organization`, `Relationship`: private relationship graph within a partition.
- `Engagement`, `Project`, `Matter`: bounded units of collaboration with lifecycle and ownership.
- `Interaction`, `Meeting`, `MessageReference`: communication metadata and linked source evidence.
- `Decision`, `Commitment`, `Task`, `Milestone`, `Risk`: operational state with assignee and due logic.
- `Note`, `Artifact`, `TranscriptReference`: authored or imported knowledge; raw transcript payloads
  remain vault-class until their source-specific custody gate passes.

### Provenance and operation

- `Source`, `SourceCursor`, `SourceEnvelope`, `ImportRun`, `NormalizationReceipt`.
- `Tag`, `Link`, `SavedView`, `SearchDocument`, `SearchReceipt`.
- `AutomationRule`, `AutomationRun`, `Job`, `OutboxEvent`, `Notification`.
- `AuditEvent`, `RetentionRule`, `LegalHold`, `ExportBundle`, `RestoreReceipt`.

All commands produce domain events and audit records in the same transaction. API responses expose
projection DTOs, never persistence rows.

## Primary user journeys

1. Capture a note, file, URL, or message reference into an explicit partition in under one minute.
2. Process the inbox: classify, link, assign, convert to commitment/task/decision, or archive.
3. Search across authorized partitions, then narrow by person, project, source, type, time, or tag.
4. Open a person, organization, engagement, or project and see a provenance-backed timeline.
5. Review commitments due, waiting-on, stale, at risk, recently decided, and recently changed.
6. Prepare for a meeting from relevant history, open commitments, decisions, and source receipts.
7. Record a decision and atomically propagate resulting tasks, notifications, and audit events.
8. Export one partition in a portable, redacted, checksummed bundle and restore it into an isolated
   test environment.
9. Grant a collaborator only the minimum portal view/actions, preview that view as the collaborator,
   and revoke it without changing owner custody.
10. Let an agent query or propose operations through MCP, while every mutation requires the same
    policy decision, idempotency key, audit event, and bounded receipt as the API.

## API and event contracts

- Versioned REST resources and commands under `/v1`; OpenAPI is generated and drift-checked.
- Cursor pagination, stable sort keys, conditional writes, idempotency keys, and RFC-style problem
  responses are mandatory from the first mutable endpoint.
- Domain events are versioned envelopes containing event id, partition, aggregate, sequence,
  causation, correlation, actor, schema version, occurred/recorded times, and redacted payload.
- Webhooks are disabled until signing, delivery retry, replay protection, and destination ownership
  predicates pass.
- MCP tools are thin adapters over application commands/queries; they do not duplicate business
  logic or bypass audit.

## Security and privacy model

The threat model includes accidental cross-client disclosure, compromised collaborator sessions,
malicious imports, prompt injection in captured content, forged webhooks, connector overreach,
log/trace leakage, backup omission under row security, and agent confused-deputy behavior.

Controls include default-deny policy, forced RLS, service-role separation, field-level redaction,
content quarantine, safe rendering, CSP, CSRF protection, rate/size limits, signed receipts,
idempotency, dependency and secret scanning, audit integrity checks, and backup verification with
`row_security=off` failure detection. Authentication is an adapter over OIDC/session primitives;
the authorization core never depends on one identity vendor.

## Deliberate exclusions from the first Omega

- Billing, payments, public marketing, marketplace distribution, and self-service tenancy.
- Automatic collaborator invitation or email sending.
- Live client content, credentials, or transcript movement without source-specific gates.
- A required vector database, proprietary queue, proprietary object-store API, or fixed AI model.
- Native mobile applications. The responsive web/PWA surface owns the first mobile experience.

These are excluded capabilities, not silently removed promises. Their extension points and gates are
part of the architecture; implementation waits for evidence that the capability is needed.
