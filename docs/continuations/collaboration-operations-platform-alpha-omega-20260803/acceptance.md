# Acceptance and Omega contract

## Definition of product completion

The suite is at Omega only when the target repository's `scripts/omega.sh` exits zero twice on the
same exact head and the second run creates no diff, no new receipt, and no unowned residual. Omega
is a conjunction of preserved phase receipts; it is not a fresh unbounded rerun of every heavy test.

## Required gate families

### Contract and compilation

- Lockfile is frozen and reproducible.
- Formatting, lint, strict typecheck, package-boundary checks, and build pass.
- JSON Schema, generated TypeScript, OpenAPI, event catalogs, database schema, and MCP tool catalogs
  have no uncommitted generation drift.
- Every migration applies from empty, upgrades from the previous supported schema, and is exercised
  on an ephemeral database. Destructive down-migrations are not run against durable data.

### Partition and disclosure safety

- A generated principal × partition × role × action matrix proves default deny.
- Row-level security is enabled and forced on every partitioned table.
- Cross-partition IDs, foreign keys, search, exports, jobs, caches, notifications, and MCP tools have
  negative tests proving they cannot leak records.
- API response schemas reject undeclared fields, and snapshot tests contain no secret/private shapes.

### Functional journeys

Playwright tests cover capture, inbox processing, search, timeline, commitment review, meeting prep,
decision-to-task propagation, scoped portal preview/revocation, export, and isolated restore. Tests
assert user-visible behavior rather than implementation selectors, following current official
[Playwright guidance](https://playwright.dev/docs/best-practices).

### Ingest and automation

- Duplicate source envelopes are harmless; cursor replay produces byte-equivalent normalized state.
- Malformed or hostile payloads enter quarantine/dead-letter storage with bounded diagnostics.
- Jobs survive worker interruption, cannot execute the same external effect twice, and preserve
  causation/correlation through retries.
- Automation dry-run, approval, execution, failure, retry, and cancellation each emit receipts.

### Security and supply chain

- Threat model and abuse cases map to executable controls.
- Secret scan, dependency audit, license policy, SAST, container scan, and SBOM generation pass.
- Session, CSRF, CSP, rate limit, upload limit, safe-rendering, webhook-signature, and prompt-content
  isolation tests pass where those surfaces exist.
- Logs, traces, metrics, errors, screenshots, fixtures, and test artifacts pass the privacy scanner.

### Reliability and custody

- Health/readiness probes, graceful shutdown, job draining, migrations, and rollback runbooks pass.
- Backup is checksummed, encrypted through an adapter, restored into an isolated environment, and
  compared by logical counts plus sampled content hashes.
- Recovery point and recovery time measurements are recorded from the synthetic trial.
- Operational alerts have owner, severity, predicate, and runbook; no alert is prose-only.

### Accessibility and experience

- Keyboard-only operation, focus management, semantic landmarks, contrast, reduced motion, screen
  reader labels, responsive layouts, loading/empty/error/offline states, and destructive-action
  confirmations are covered by automated and manual receipts.
- Owner and collaborator views are tested as distinct personas; no owner-only navigation or counts
  appear in collaborator projections.

## Performance budgets

Budgets are measured against a versioned synthetic corpus and recorded rather than guessed. Initial
admission targets are p95 API reads under 300 ms, p95 commands under 500 ms excluding external work,
search under 500 ms at the trial corpus size, and no page shipping more than its declared bundle or
request budget. A measured regression requires an owned exception or repair packet.

## Release levels

1. `foundation`: contracts, policy, storage, and gates; no meaningful UI promise.
2. `owner-alpha`: complete synthetic owner journeys on local Compose.
3. `owner-beta`: hardened private deployment artifacts and restore proof; deployment still gated.
4. `partition-pilot`: one explicitly authorized source partition, imported through dry-run then
   accepted with custody receipt.
5. `collaborator-pilot`: one explicitly authorized scoped portal principal; no ambient grants.
6. `omega`: all declared capabilities green, residuals owner-routed, exact-head fixed point.

## Stop and successor conditions

Agy does not ask the operator routine questions. It derives from doctrine, records an ADR, and
continues. At a genuine retained gate it records `BLOCKED: <atom>` once in the owning registry,
continues all independent packets, and emits a finite successor capsule if runway or context ends.
It may declare `settled` only when this contract and the machine-readable DAG agree.
