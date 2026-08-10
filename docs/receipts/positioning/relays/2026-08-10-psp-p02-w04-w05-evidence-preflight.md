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
- Current W03 parent head: `c16c9f48056aff76b892568550ce5cbadecca839`
- Hardened implementation checkpoint: `488e55b9c25c8208cdf2e08ab1e6dced8524e3be`
- Review-correction checkpoints: `8f93fc27abcb4cb6f32b42b2569091bb73a4a436` and
  `82f4795ba32f8ac7c3fc9f3d3441e7b111891540`
- Late-audit correction parent: `eabee3f034d9072b6699e3862b7d543c9ffa1d65`; the current PR
  head supersedes it with the seven-finding correction batch.
- Current live W03 dependency head at correction time:
  `322e2d583b04cc0157c568b654305debb66c1904`.
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction; this
  remains a reversible preflight, not a claimed formal completion.

## Verified current state

| Item | Live state |
|---|---|
| Selected packet denominator | 3, exactly the W03 public flagship triad |
| Exact reviewed code checkpoint | Fetch PR #2310 for the current exact head; it supersedes late-audit parent `eabee3f034d9072b6699e3862b7d543c9ffa1d65` |
| Private repository identity guard | Derived from the redacted W01 public-repository projection; aggregate result 0 unregistered controlled identities, with no private names loaded or emitted |
| Public workflow anchors | 3 successful exact-head workflow snapshots |
| Public endpoint anchors | 3 HTTP 200 snapshots |
| Indexed metrics made publishable | 4 exact statements across the 3 bounded packets |
| Explicitly withheld | usage, installs, customers, adoption, revenue, rankings, and private implementation |
| W03 / W04 / W05 issue state at preflight | open / open / open |
| Task-specific predicates | `python3 scripts/flagship-evidence.py --verify-live --json` passed; formal `--verify-work` commands intentionally not run |
| Focused regressions | `python3 scripts/tests/flagship-evidence.test.py` passed 40 tests, including packet-level bounded-claim parity, derived public-identity custody, malformed collection handling, immutable full W08 adjudication binding, section-8 metric parity, predecessor receipt enforcement, and interrupted response-body handling |
| Parent privacy guard | `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w03-flagship-proof-preflight` passed over the full W04/W05 diff: 314 repositories, 235 public, 79 private, with no private repository token added |
| Scoped verification | One bare `scripts/verify-scoped.sh` batch passed all implicated gates on the final late-audit correction tree |
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
- Restricted live fetches and every redirect hop to the selected public hosts, rejected embedded
  credentials and nonstandard ports, and bounded all response bodies before parsing.
- Covered every consumed input in the scoped gate, including recursive packet paths and the claims
  ledger, and proved the resolver selects the evidence gate for a packet-only change.
- Bound workflow API and human URLs to one run in the selected repository and require the live API
  response to return the same repository and URLs.
- Derived the collector and export-format denominators from complete, head-pinned Git trees rather
  than accepting predeclared term presence as an exact count.
- Bound the 13 imported W08 wording and receipt sets to the immutable source head, path, blob,
  artifact SHA-256, and canonical projection SHA-256; the projection now includes all four layer
  dispositions and `publishable_status` as well as wording and receipts.
- Made packet Markdown a validated projection of each indexed packet-level bounded claim, not only
  its metric sentences.
- Replaced the author-declared private-name count with a full-surface, count-only identity guard
  against the redacted W01 public repository projection and registered that source as a gate input.
- Made claims-ledger section 8 a parsed, exact projection of the packet metric denominator,
  statuses, observed values, and public-safe wording.
- Made dependency declarations follow their live issue owners through the W03 -> W04 -> W05
  closure order and invoke the canonical latest-marked-receipt predicate for every closed
  predecessor while leaving the current open/open/open preflight valid.
- Converted timeout, reset, incomplete-read, and other response-body I/O failures—including HTTP
  error-body reads—into public-safe machine-readable evidence errors.

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
- Pull request: https://github.com/organvm/limen/pull/2310 (ready, stacked on W03); all review
  threads through the late seven-finding audit are resolved. Do not merge it while dependencies
  remain open.

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-p02-w04-w05-evidence-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, approval, issue state, or permission.
