# Domain vocabulary and partition model

## Terms

- `partition`: The non-transitive security and custody boundary for one collaboration/client.
- `record`: A durable object persisted in platform state (notes, artifacts, commitments, decisions,
  meetings, etc.).
- `principal`: Owner, service, collaborator, or agent identity currently authenticated for a request.
- `capability`: A scoped permission required for each action and field visibility requirement.
- `provenance`: Source, cursor, version, actor, and time evidence carried by every durable record.
- `envelope`: Raw source payload container carrying external IDs, checksums, and source revision.
- `receipt`: Immutable evidence of predicate success, mutation request, and outcome.
- `outbox`: Durable queue mechanism coordinating API commands with worker execution.
- `policy envelope`: Decision record emitted before data leaves policy boundaries.

## Canonical relationships

- A partition contains partitions' owners, collaborators, persons, projects, engagements, and
  evidentiary assets.
- A principal may hold many role assignments across partitions but only explicit grants grant actions.
- No relation crossing partitions is permitted unless a policy-checked bridge is explicitly recorded.
- Search, export, and automation all consume the same policy envelope and partition context as direct
  API flows.

## Record constraints

- Every durable object has immutable identifiers, partition IDs, creator metadata, lifecycle state, and
  classification labels.
- Deletions are recoverable defaults. Physical purge remains gated and signed.
- Cross-partition references can be recorded only as approved, redacted references with explicit policy.
