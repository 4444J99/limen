# ADR 0001: Private partition boundary as primary trust anchor

## Status

Accepted

## Context

The platform must host records from multiple collaborations without enabling ambient data transfer. The
primary safety constraint is cross-partition non-disclosure.

## Decision

Adopt `partition_id` as a mandatory durability and policy dimension for every object, with default-deny
authorization and forced row-level security for partitioned tables.

## Consequences

- Any flow that cannot express partition context is rejected.
- Cross-partition references require explicit approvals and redacted representation.
- UI/Portal/MCP/rules all consume the same partition+policy checks.
