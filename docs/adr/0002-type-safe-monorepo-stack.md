# ADR 0002: TypeScript monorepo and schema-first service seam

## Status

Accepted

## Context

Implementation spans API, web, worker, CLI, MCP, and shared domain/services. Coordination must stay
low-friction while preserving typed boundaries and deterministic validation.

## Decision

Use a schema-first TypeScript monorepo with Fastify, Next.js, PostgreSQL, and adapter-based object
storage. Enforce strict TypeScript and explicit package boundaries from the start.

## Alternatives considered

- Framework-heavy all-in-one stack: rejected for policy coupling risk.
- Language-divergent multi-runtime stack: rejected due to schema drift risk in early phases.
- NoSQL-first canonical storage: rejected for deterministic policy audit and RLS requirements.

## Consequences

- Shared contract generation and strict compile gates are mandatory.
- Package boundary checks become a first-class quality gate.
