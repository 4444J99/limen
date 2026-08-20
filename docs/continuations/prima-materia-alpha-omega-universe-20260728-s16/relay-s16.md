# Prima Materia α→Ω recalibration relay — S16

## Decision

Continue the existing campaign, but redirect it. Do not restart from scratch and do not
automatically add another universe adapter.

The S2–S15 lineage contains valid, remotely durable control-plane and source-coverage work.
Discarding it would not change any live blocker. The next independently executable packet is the
β streaming custody executor because it is reversible code work and is a prerequisite for any
repository, private-data, or storage mutation.

The machine-readable predicate matrix is `recalibration.json`.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s16`.
- Admitted capsule commit: `a84ca54b6398ae095933a083d3ef0a8936f592c7`.
- Capsule receipt SHA-256:
  `d84a02fc8ca590557fc0f1633d60e1aa424df7720b32a02f47824ee1b4e9b1c2`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- S16 preserved that deadline; it did not create a fresh eight-hour clock.

## Live predicate matrix

| Plane | Live truth | Consequence |
|---|---|---|
| α | PR #1606 remains open and clean at `f002f973…`; required `python` and `pr-gate` are green. Remote `main` and the installed immutable runtime both remain `4a86f382…`. | `merged_and_installed = false`; do not mutate custody, source data, or reclaim state. |
| β custody | The authenticated AES-256-GCM byte store exists, but it buffers the whole object and returns the whole restore in memory. There is no streaming `put_path`, streaming restore, interruption resume, source-drift guard, or dual-device restore receipt. | Implement and test the bounded executor before any real custody batch. |
| Devices | Archive4T and T7Recovery are mounted, writable, and resolve through distinct live APFS physical stores. | Physical independence is currently available, but it is not a restore proof and must be re-proven per batch. |
| Estate | The last frozen wave contains 84 repository roots, 18 storage roots, and 113 source instances. Its reclaim census is incomplete: scanned `0`, failures `1`, candidate count `null`, no plan digest. | `null` is not zero; no reclaim is admitted. The old wave also predates the S15 source snapshot and cannot be reused as current universe proof. |
| Storage | Internal free space is 157.6 GiB, below the formal 200 GiB predicate. | The storage fixed point is false even though an older planner snapshot reported zero automatic safe roots. |
| Universe | 5 of 11 registered source families are executable (15 of 33 enumerator refs); 6 families and 18 refs remain missing. The latest public lower bounds remain 19 projects and 14 collaborators. The live GitHub snapshot adds 308 repository rows, 4 access rows, and one Projects debt row. | Source coverage, canonical-project completeness, all-project builds, collaborator reconciliation, and the six-rung universe fixed point are false. |
| λ | 0 of 13 original predicates pass. Both prior audits are incomplete and their state digests differ. | Equal complete λ audits: `0`. |
| Ω | One protected owner blocker remains and no complete Ω audit exists. | Equal complete Ω audits: `0`; the career lane remains untouched. |
| Host | The S16 writer lease is admitted. Heavy work is denied at the observation point because swap is 26.1%, while VITALS reports `ok`. | Continue light inspection and bounded source work; do not force a heavy scan. |

## Why β is next

The store currently proves cryptography and tamper detection for in-memory bytes, not operational
custody for repository and private-data roots. The β packet must add:

- bounded, streaming, resumable `put_path`;
- streaming restore to a caller-selected new path without plaintext staging;
- authenticated partial-state and manifest handling;
- exact source identity and before/after drift checks;
- explicit disk, rollback, RAM, file-count, network, and wall-time claims;
- tests for large inputs, interruption/resume, tampering, source drift, symlinks, modes, and
  destination fail-closed behavior; and
- a two-store batch interface that rejects identical physical parents and can emit independent
  restore receipts.

This packet must use isolated temporary stores only. It must not copy, delete, evict, or reclaim any
real repository, private root, or storage inventory item. Actual dual-device custody remains gated
until α is merged and installed and this executor passes.

## Session and local lifecycle

- S2 through S15 are clean, inactive, exact-HEAD remote-preserved, and physically removed locally.
- S16 is the sole local Prima Materia worktree.
- The separate laptop-wide recovery S18 lineage and the career lane were not touched.
- Progress email is sent only after this recalibration receipt is committed and remotely exact.

## Retained owner gates

- Anthony owns merge-queue admission for PR #1606.
- Runtime installation and installed-SHA attestation follow that merge.
- GitHub Projects scope remains a credential-wall atom; do not refresh it here.
- No destructive, credential, paid-spend, public-send, runtime, custody, eviction, or reclaim action
  is authorized by this recalibration.
