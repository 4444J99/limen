# Shared-Keeper Reacceptance Ledger v2

This directory is the redacted, durable index for the historical recovery
campaign that begins at `2026-07-12T15:37:35Z`. It freezes exactly 29
top-level Claude sessions, 11 Claude workflows, 65 historical pull requests,
and the 208 review findings observed at the recovery boundary. Provider and
executor names record provenance only; no keeper is superior to another.

The v2 contract separates the frozen 105 historical rows from later recovery
work:

- `attempts` owns source lineage, executor identity, spend, outputs, effects,
  predicates, owner surfaces, and durable receipts exactly once.
- `remedies` admits newer pull requests, commits, reversals, deployments,
  checkpoints, and owner receipts without changing the historical denominator.
- `coverage` is the many-to-many crosswalk from remedies to historical rows
  and individual finding discussions.
- `findings` preserves every original discussion URL and permits a terminal
  disposition only after the original thread is resolved.
- `scope.json` binds every row to the frozen redacted source atom through a
  row-anchored manifest digest. Editing both a row and its attempt cannot
  substitute unrelated lineage.
- Every row embeds its complete v1 payload, and every validation recomputes
  the frozen v1 denominator digest. Migration-time checks alone cannot stand
  in for release-time proof.
- `owner_evidence` feeds five typed adapters. `completion_gates` is derived
  from those adapters and cannot be asserted manually.
- Owner-adapter and effect-owner evidence is authenticated against
  scope-pinned public keys. A named owner, a passing status string, or a shared
  local receipt cannot authenticate itself; unprovisioned owner keys remain an
  explicit release blocker.
- `evidence_digest` recursively excludes volatile timestamps, registry order,
  summaries, and fixed-point attestations. Two complete refreshes with the
  same digest prove semantic stability only when two distinct fresh owner
  receipts bind those exact refresh records.

An accepted exact-head remedy stores the complete
`limen.pr_review_gate.v1` receipt. A string such as
`review_gate_status: accepted` is not evidence. The ledger refreshes every
remedy from GitHub, requires the remedy to be merged, binds the full receipt
to the attempt that owns the live remedy URL, derives CI success from the
current CheckRun/status state, and requires a successful
`limen.pr_review_gate.v1` CheckRun from the configured dedicated App on that
exact head. Generic Actions cannot satisfy the App boundary.

Structural validity is not campaign completion:

```bash
# No writes; exits zero when the v2 document is structurally honest.
python3 scripts/reacceptance-ledger.py --check

# No writes; exits zero only when every release predicate passes. A candidate
# YES is re-read from GitHub and must use a current snapshot.
python3 scripts/reacceptance-ledger.py --require-release-ready

# Read GitHub, preserve adjudicated registries, and write only when explicit.
python3 scripts/reacceptance-ledger.py --refresh --write

# After explicitly editing attempts/remedies/coverage/owner evidence, rederive
# those registries, perform a fresh owner read, and reset fixed-point history
# to one live refresh. A second ordinary refresh is still required.
python3 scripts/reacceptance-ledger.py \
  --refresh --accept-edited-registries --write
```

The tracked snapshot is structurally valid and honestly not release-ready:
105 historical rows remain `repair_required`, all 208 findings remain open,
ten live replacement/umbrella PRs are registered as `repair_required`, and no
remedy or attempt has yet been accepted. The dedicated review App,
owner-attestation keys, and frozen private-content manifest are unprovisioned;
equal local refresh digests alone cannot pass the continuation gate.

Files:

- `scope.json` freezes row, source-atom, baseline-open-PR, finding, privacy,
  known-effect, dedicated-App, and cutoff denominators.
- `ledger.json` is the current v2 snapshot.
- `predicates.md` defines terminal row, remedy, finding, and release evidence.
- `continuation.md` is the reproducible successor capsule.
- `external-actions.md`, `privacy-containment.md`, and `incidents.md` remain
  indexes; prose in those files cannot satisfy owner evidence.

Raw prompts, private paths, personal records, full private hashes, and
credentials remain in their private owners.
