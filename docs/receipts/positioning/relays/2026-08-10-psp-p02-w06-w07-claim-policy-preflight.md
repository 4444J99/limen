---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected preflight task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w06-w07-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W06/W07: claim policy and quarantine preflight

## Routing

- W06 issue: #2178 — formal dependency: #2177 (W05).
- W07 issue: #2179 — formal dependency: #2178 (W06).
- Branch: `codex/psp-p02-w06-w07-preflight`.
- Draft pull request: https://github.com/organvm/limen/pull/2311, stacked on PR #2310.
- Current W04/W05 parent head: `3a752d530633c8a2ec4b7942e325b4838e56c233`.
- Initial W06/W07 implementation: `2a0550862091a976b756034d4ddfa3965fd206ec`.
- Exact verified implementation head: `ef4ae2ed12af5b5a27a5d26beeb33ee502188b28`.
- Published remote checkpoint: `ef4ae2ed12af5b5a27a5d26beeb33ee502188b28`
  before this relay refresh; fetch PR #2311 before resuming.
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction.
- This is preflight-only implementation. It carries no W06/W07 completion receipt,
  issue closure, merge authority, publication, or release effect.

## Implemented preflight seam

- `scripts/claim-policy.py` consumes the W05-owned, public-safe claim-ledger
  export contract. It rejects unsupported, stale, future-dated, private/restricted,
  forbidden, withdrawn, invalid-window, and source-changed claims without fetching
  data or exposing claim wording in its verdict. Public source anchors must be
  credential-free HTTPS URLs.
- `scripts/claim-surface-quarantine.py` consumes a complete generated-public-
  surface manifest, proves that every rejected claim is covered, validates every
  bounded marker before writing, rejects traversal/symlink/duplicate surfaces, and
  emits quarantined staging copies only. Source artifacts remain unchanged; no
  deploy or publishing pathway is called.
- `scripts/claim-quarantine-drill.py` runs a hermetic false-claim drill across
  every fixture-declared public surface. The fixture contains synthetic text only.
- `docs/positioning/program/CLAIM-CORRECTION-PROTOCOL.md` specifies incident
  classes, correction-record fields, source-change handling, restoration
  criteria, and the exact W05 integration contract. It does not modify the W05
  ledger or W04/W05 evidence packets.

## Verified preflight state

- `bash scripts/run-pytest-hermetic.sh scripts/tests/test_claim_policy.py -q`
  — 9 passed.
- `python3 scripts/claim-quarantine-drill.py --fixture-dir scripts/tests/fixtures/positioning-claim-drill --json`
  — passed; two synthetic generated public surfaces quarantined, publication effect `none`.
- `python3 scripts/check-gates.py` — passed with the existing recorded
  `cli/**` deploy-trigger disposition.
- `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w04-w05-public-evidence-preflight`
  — passed over the full W06/W07 diff: 314 repositories, 235 public, 79 private,
  with no private repository token added.
- `scripts/verify-scoped.sh` — all 23 implicated cheap-wave gates passed on exact
  implementation head `ef4ae2ed12af5b5a27a5d26beeb33ee502188b28`.

## Dependency boundary and formal sequence

1. Keep W06 unclosed until W05 has a valid merged exact-head receipt and a
   schema-conforming ledger export.
2. Bind the real generator to the documented export and surface-manifest seam;
   generate into a fresh staging directory, then run the policy gate before any
   release review.
3. Add a W06 marked receipt naming `claim-policy.py` plus its focused tests as
   the non-circular predicate. Run the W06 `--verify-work` predicate bare only
   after that receipt and dependency state are live.
4. Keep W07 unclosed until W06 is formally complete. Then attach a W07 receipt
   naming the synthetic full-surface drill, run its `--verify-work` predicate
   bare, and close only if it passes against the merged exact head.

## Rollback

Disable promotion from the staged generation directory and retain the last
known-green public artifacts. Restore a quarantined claim only after a corrected
public claim export passes the policy gate and the regenerated staged manifest is
complete. No public output was changed by this preflight.

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-p02-w06-w07-claim-policy-preflight.md. Preserve W06->W05 and W07->W06 formal dependency gates; integrate only through the documented W05 export and staged-surface manifest seam.
```
