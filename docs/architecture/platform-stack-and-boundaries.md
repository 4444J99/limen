# Platform architecture and stack decisions

## Chosen stack shape

- Monorepo organization with strict TypeScript boundaries.
- API boundary: Fastify for command/query validation and OpenAPI generation.
- Owner console: Next.js App Router with a policy-aware client.
- Worker model: persistent durable-job execution with deterministic outbox processing.
- Storage: PostgreSQL as authoritative state, S3-compatible object storage through adapters.
- Integration model: connector SDK + synthetic-only fixtures before any live source ingest.

## Partition and policy boundary

- Partition IDs are required fields for all durable records.
- Policy checks are centralized and executed before database mutation, job enqueue, search indexing,
  portal projection, MCP access, and export.
- Row-level security is mandatory and forced for partitioned durable data.

## Rejected alternatives

- Hard-coded static frontend-only persistence with no durable outbox/jobs model.
- Native dependency on proprietary vector-only search before deterministic SQL search is complete.
- Monolithic queue vendor introduced before pressure metrics and retry logic justify externalization.
- Fixed paid model/provider lock-in at architecture definition time.

## Runtime strategy

- Dependencies and versions are derived during genesis by local probe and pinned in lockfiles.
- CI and acceptance are packetized; each packet writes receipt evidence before proceeding.
