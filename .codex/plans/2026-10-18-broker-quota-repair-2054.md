# Conduct persistence quota repair — 2026-10-18

Goal: eliminate snapshot write amplification behind limen#2054 without weakening storage admission.

Observed base: b6a4f208480da3d80005d753ee2a5b09b8b95e0b (conduct files unchanged at live main 15dc46ff).
Direct human request: review, critique, plan and implement; use a team.

Review: steady heartbeats already write one row. Cold mutations rewrite every state chunk and delete the prior generation. Identical saves still attempt legacy deletion. The rollback drain writes on read requests when the heartbeat overlay flag is disabled. The launcher correctly fails closed on an unavailable authoritative census.

- [x] Add a conduct-specific differential row store, retaining the generic snapshot store for private-board.
- [x] Atomically commit only changed map entries, lifecycle events, counters and a state manifest. Chunk oversized records. Keep all audit history.
- [x] Preserve v1 reads, retain original checkpoint during migration, fail closed on incomplete selected records, and materialize exact v1 state for rollback.
- [x] Keep read requests write-free with either persistence flag; defer rollback materialization to a successful mutation.
- [x] Prove equal registration write/delete counts with 0, 2,400 and 12,000 history events, inject every commit-boundary failure, test corruption and rollback.
- [ ] Run focused tests, one scoped verification batch, independent review, and publish through the repository PR rail.

General storage write cost is proportional to changed records; bulk lease expiry legitimately changes many records. A simple registration target is six puts (three identity records, event, sequence counter, manifest), zero deletes. Heartbeat target remains one put, zero deletes.

The existing LIMEN_CONDUCT_STEADY_HEARTBEAT_OVERLAY=0 rollback switch will select legacy cold persistence too. Reads continue reconstructing authoritative state without writes; one successful mutation must materialize the v1 checkpoint before restoring an older binary.

Production quota recovery, deployment, native Agy canary, and #2054 closure remain separate acceptance predicates. No billing change or state deletion is authorized or required.

Runbook: docs/architecture/conduct-persistence.md. Review corrections adopted: immutable cache bases, changed-record hashing, rewritten migration rows, symmetric byte bounds, transaction retry and overlay-fold failure tests, and an atomic old-reader rollback fence.
