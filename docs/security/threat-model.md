# Threat model and security posture

## Threat actors

- Compromised collaborator credential or session replay attack.
- Malicious or accidental source payload injection.
- Connector overreach or privilege misuse.
- Retained artifact leakage via logs, telemetry, exports, or search indexes.
- Queue/job replay and duplicate command execution.
- Credential movement without explicit gate.

## Assets

- Partition membership and grants.
- Raw source envelopes and attachment hashes.
- Decision history, commitments, and legal-risk state.
- Automation and portal action records.
- Backup artifacts, restore manifests, and run receipts.

## Misuse cases

1. Cross-partition disclosure through query join, search, or export leakage.
2. Replay-driven duplicate side effects through worker crashes.
3. Log or trace exposure of private payload fields.
4. Connector-induced data pull without cursor/provenance validation.
5. Unauthorized collaborator action under stale grants or revoked sessions.

## Controls

- Default-deny policy at policy and SQL layers.
- Forced row-level security across partitioned tables.
- Idempotency keys and replay-safe receipt design for command and automation runs.
- Redaction at API and transport boundaries for private fields.
- Outbox-driven side-effect mediation and deterministic retries.
- Synthetic fixture first; live source materialization only under retention and authorization gates.
