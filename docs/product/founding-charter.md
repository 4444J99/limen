# Collaboration Operations Platform founding charter

## Purpose

Build a private collaboration control plane that captures and preserves records for every active
collaboration and client while preventing cross-partition disclosure by design.

The first user is the owner/operator. Collaborators receive scoped projections only; no collaborator
inherits or infers access to another partition by default.

## Core invariants

1. Every durable artifact is owned by one explicit partition.
2. Authorization is default-deny for every write and read path.
3. Raw source payloads are admitted as append-only envelopes and must be processed through policy
   and provenance controls.
4. All side effects are auditable, reproducible, and represented by receipts.
5. Synthetic data is the only content source until retention gates authorize live imports.

## Persona model

- Owner: creates partitions, manages policy, reviews commitments, triggers actions.
- Collaborator principal: receives a scoped projection over a single partition, no implicit lateral
  visibility.
- External source lane: owns source-of-truth references and can feed the platform only through a
  mediated connector/acceptance path.
- Operator: performs controlled administration, diagnostics, restore, backup, and migration work.
- Automation principal: executes policy-checked mutations with idempotency and receipts.

## Exclusions from Alpha

- Billing/payments and self-serve multi-tenancy.
- Public marketing funnels, ambient invites, or open user signup.
- Automatic collaborator notifications until the notification packet family is implemented.
- Native mobile-first client, proprietary model dependency, or fixed lockstep queue/queue vendor.

## Governance and safety defaults

- No direct grants across partitions.
- No raw transcript/content migration without explicit custody gates.
- No production deployment, DNS edits, collaborator invitation expansion, or credential movement outside
  explicit retained-gate ownership.

## Sources copied into immutable lineage

See `/docs/product/founding-plan-lineage.md`.
