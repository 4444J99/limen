---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected preflight task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w04-w05-public-evidence-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W04/W05: public flagship evidence and metric preflight

## Routing

- Program work IDs: `PSP-P02-W04`, `PSP-P02-W05`
- Issues: https://github.com/organvm/limen/issues/2176 and https://github.com/organvm/limen/issues/2177
- Formal predecessor: https://github.com/organvm/limen/issues/2175
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w04-w05-public-evidence-preflight`
- Stacked base: `codex/psp-p02-w03-flagship-proof-preflight`
- Initial W04/W05 implementation commit: `23400cee7ffbf95e66f3837f0ef3f02f47bd17fb`
- Current W03 parent head: `528c94d31a426f3a9cac29a72cd38bc942d45171`
- Exact verified implementation head: `47a43e7e8065a2cba3a1319855fa257280c9b160`
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction; this
  remains a reversible preflight, not a claimed formal completion.

## Verified current state

| Item | Live state |
|---|---|
| Selected packet denominator | 3, exactly the W03 public flagship triad |
| Exact remote branch checkpoint | `47a43e7e8065a2cba3a1319855fa257280c9b160` before this relay refresh; fetch PR #2310 before resuming |
| Private repository names in public artifacts | 0 |
| Public workflow anchors | 3 successful exact-head workflow snapshots |
| Public endpoint anchors | 3 HTTP 200 snapshots |
| Numeric claims made publishable | 3 bounded, dated statements |
| Explicitly withheld | usage, installs, customers, adoption, revenue, rankings, and private implementation |
| W03 / W04 / W05 issue state at preflight | open / open / open |
| Task-specific predicates | `python3 scripts/flagship-evidence.py --verify-live --json` passed; formal `--verify-work` commands intentionally not run |
| Focused regressions | `python3 scripts/tests/flagship-evidence.test.py` passed 9 tests, including repository substitution, duplicate-source, path-traversal, and nonnumeric-metric failures |
| Parent privacy guard | `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w03-flagship-proof-preflight` passed over the full W04/W05 diff: 314 repositories, 235 public, 79 private, with no private repository token added |
| Scoped verification | `scripts/verify-scoped.sh` passed all 22 implicated cheap-wave gates on exact head `47a43e7e8065a2cba3a1319855fa257280c9b160` |
| External effects | branch/PR staging only; no merge, publication, issue-state, or account change |

## Completed work

- Added one public-safe packet per selected flagship under `docs/positioning/evidence/`.
- Added `flagship-evidence.yaml`, a machine-readable index that requires the W03 triad exactly,
  rejects private-evidence dependency, and preserves W03 -> W04 -> W05 formal ordering.
- Added `scripts/flagship-evidence.py` and focused regression tests. Live validation checks public
  workflow conclusions and exact heads, endpoint status, JSON snapshot values, and required metric
  terms rather than accepting HTTP success alone.
- Restored the canonical claims ledger on this stack and added a W04/W05 section that places all
  cohort numeric claims under the same authority and withholds the unsupported classes.
- Reconciled the ledger to the stable W01 denominator of 314 repositories (235 public, 79 private),
  retained earlier counts as superseded history, and withheld stale composite status counts.
- Bound every packet repository to the exact W03-selected public repository, required one public
  workflow plus one public endpoint, and rejected traversal, non-HTTPS, or nonnumeric evidence rows.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Keep the proof set at three | The W03 matrix selects exactly three public flagships; W04 must not promote alternates. |
| Do not create an encrypted addendum | No selected claim needs private evidence. Existing custody may be used only if later diligence requires it. |
| Use exact snapshot comparisons | A changed count fails until a reviewer refreshes the dated packet, preventing stale numbers from silently inheriting currentness. |
| Treat the collector count conservatively | Four implemented collectors is repository-asserted with public source/deployment anchors; it is not fifty-state deployment. |

## Next actions

1. Confirm W03 has closed with a valid receipt and refresh the W03 matrix against its merged exact
   classification before taking any W04 formal-completion action.
2. Re-run `python3 scripts/flagship-evidence.py --verify-live --json` and the scoped verifier on
   the exact refreshed W04 head. If a live metric changes, update the dated packet and ledger row
   before a new receipt is proposed.
3. Only after the W04 receipt verifier passes and its issue closes, repeat the current-source check
   for W05, generate its receipt, and run its formal verifier. Do not close either issue from this
   preflight branch alone.

## Risks and prohibitions

- Human gates still unpulled: formal receipt/issue closure is blocked by W03, then W04.
- Sensitive/private boundary: no private names, paths, hashes, customer data, or invented
  encrypted-addendum contents may enter these packets, PRs, or issue receipts.
- Files and sibling work that must not be touched: `tasks.yaml`, the W03/W02 branches, live profile
  generators, and any deployment or account surface.
- Rollback: withdraw a failed packet/metric from public use, preserve the dated record and
  correction history, then regenerate dependent wording only after fresh evidence exists.

## References

- Flagship selection: `docs/positioning/flagship-proof-set.yaml`
- Packet index: `docs/positioning/evidence/flagship-evidence.yaml`
- Claims authority: `docs/positioning/claims-ledger.md`
- Pull request: https://github.com/organvm/limen/pull/2310 (draft, stacked on W03); do not merge it while dependencies remain open.

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-p02-w04-w05-evidence-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, approval, issue state, or permission.
