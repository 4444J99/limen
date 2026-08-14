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
- Current W04/W05 PR head observed during this refresh:
  `eabee3f034d9072b6699e3862b7d543c9ffa1d65`; this branch retains merge base
  `3a6acddc6487976cad94bc37d35608f08c182f94` and remains dependency-gated.
- Initial W06/W07 implementation: `2a0550862091a976b756034d4ddfa3965fd206ec`.
- Prior hardening checkpoints: `35ec713609ecbe0d360237e62dc3747d5a476196`
  and `bc506e819690f1cfad591091573965082409122b`.
- Final verified implementation checkpoint:
  `1b7762868dec28dc55289e670e3039a57de1513d`. It contains every policy,
  quarantine, protocol, and regression change described below; the only
  successor delta is this continuation-relay plus matching gate-registry note
  refresh. Fetch PR #2311 before resuming and compare its head to that
  implementation checkpoint.
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
  bounded marker before writing, validates the accepted-plus-rejected policy
  universe, quarantines manifest claims absent from that universe with the
  public-safe reason `absent_from_policy_report`, rejects traversal/symlink/
  duplicate surfaces, and emits quarantined staging copies only. Source
  artifacts remain unchanged; no deploy or publishing pathway is called.
- `scripts/claim-quarantine-drill.py` runs a hermetic false-claim drill across
  every fixture-declared public surface. The fixture contains synthetic text only.
- `docs/positioning/program/CLAIM-CORRECTION-PROTOCOL.md` specifies incident
  classes, correction-record fields, source-change handling, restoration
  criteria, and the exact W05 integration contract. It does not modify the W05
  ledger or W04/W05 evidence packets.

## Verified preflight state

- `bash scripts/run-pytest-hermetic.sh scripts/tests/test_claim_policy.py -q`
  — 18 passed at exact implementation checkpoint
  `1b7762868dec28dc55289e670e3039a57de1513d`, including accepted/rejected
  policy-universe validation and unknown/undeclared surface-claim regressions.
- `python3 scripts/claim-quarantine-drill.py --fixture-dir scripts/tests/fixtures/positioning-claim-drill --json`
  — passed at the same exact implementation checkpoint; two synthetic generated
  public surfaces quarantined, publication effect `none`.
- `python3 scripts/check-gates.py` — passed with the existing recorded
  `cli/**` deploy-trigger disposition.
- `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w04-w05-public-evidence-preflight`
  — passed over the full W06/W07 diff: 314 repositories, 235 public, 79 private,
  with no private repository token added.
- `scripts/verify-scoped.sh` — the prior 24-gate receipt is superseded. Re-run the
  bare scoped predicate on the relay successor head and use the exact result
  recorded in PR #2311 before integration; do not reuse the stale `c8f5e268`
  receipt.

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
