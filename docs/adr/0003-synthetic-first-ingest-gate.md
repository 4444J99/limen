# ADR 0003: Synthetic-first ingest and gated live-content movement

## Status

Accepted

## Context

Platform correctness and safety are impossible if live source imports happen before policy, retention,
and custody controls are proven.

## Decision

All non-gated implementations, tests, and trials use synthetic fixtures. Live client data or
transcript import remains a retained-gated capability and is never in scope for Alpha/early Omega work.

## Consequences

- Trial corpus completeness becomes a requirement for feature validation.
- Restore and audit workflows can validate behavior without private client data.
- Source imports are implemented only after dedicated acceptance packets and explicit authorization.
