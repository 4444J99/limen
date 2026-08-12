---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-12
from: Codex desktop human-protected integration task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w04-w05-public-evidence-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W04 accepted and W05 formally admitted

## Routing

- Program work IDs: `PSP-P02-W04`, `PSP-P02-W05`
- Issues: https://github.com/organvm/limen/issues/2176 and https://github.com/organvm/limen/issues/2177
- Formal predecessor: https://github.com/organvm/limen/issues/2175
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w04-w05-public-evidence-preflight`
- Pull-request base: `main`
- Initial W04/W05 implementation commit: `23400cee7ffbf95e66f3837f0ef3f02f47bd17fb`
- Hardened implementation checkpoint: `488e55b9c25c8208cdf2e08ab1e6dced8524e3be`
- Review-correction checkpoints: `8f93fc27abcb4cb6f32b42b2569091bb73a4a436` and
  `82f4795ba32f8ac7c3fc9f3d3441e7b111891540`
- Late-audit correction parent: `eabee3f034d9072b6699e3862b7d543c9ffa1d65`; the current PR
  head supersedes it with the seven-finding correction batch.
- Accepted W03 pull-request head: `95cadbdfdbe83c22ed7158eab0df15675ae9ba7b`.
- Accepted W03 main head: `345a1ada43cc9979376690ed71361476f1ab9864`.
- W03 marked receipt: https://github.com/organvm/limen/issues/2175#issuecomment-5265611241,
  canonical receipt SHA-256 `f4d5a01afdeed0f258f3efc62a46eef4dc0c1bba537449ca2243f59cb5b762ee`.
- One-time main-integration merge checkpoint: `26f465409455fd27c51858fdef293823ae4142e3`.
- Accepted W04 main head: `a594c66980c8c40ce3f55b3a666a70ecf0ebd96b`.
- W04 marked receipt: https://github.com/organvm/limen/issues/2176#issuecomment-5265745105,
  canonical receipt SHA-256 `b2c9a4925505dc718e1f41be66fdf8e072fe03bbf677a2326f40bbfbf3fc36f5`.
- W05 formal-ready implementation source: `39fcb28627a0a01f054f1e3be02c4fcc2c3e6563`;
  the successor delta is this relay only.
- Authority receipt: human-authorized Codex continuation. This state admits W05 to the sanctioned
  merge rail; it is not itself the W05 completion receipt.

## Verified current state

| Item | Live state |
|---|---|
| Selected packet denominator | 3, exactly the W03 public flagship triad |
| Exact W05 formal-ready source | `39fcb28627a0a01f054f1e3be02c4fcc2c3e6563`; fetch PR #2328 for its relay-only descendant |
| Private repository identity guard | Derived from the redacted W01 public-repository projection; aggregate result 0 unregistered controlled identities, with no private names loaded or emitted |
| Public workflow anchors | 3 successful exact-head workflow snapshots |
| Public endpoint anchors | 3 HTTP 200 snapshots |
| Indexed metrics made publishable | 4 exact statements across the 3 bounded packets |
| Explicitly withheld | usage, installs, customers, adoption, revenue, rankings, and private implementation |
| W03 / W04 / W05 issue state | closed / closed / open |
| Accepted predecessor predicates | `--verify-work PSP-P02-W03` and `--verify-work PSP-P02-W04` passed against their latest marked receipts |
| Task-specific predicate | `python3 scripts/flagship-evidence.py --verify-live --json` passed against closed/closed/open live parity and both accepted predecessor receipts |
| Focused regressions | `python3 scripts/tests/flagship-evidence.test.py` passed 40 tests, including fully state-relative open-dependency fixtures and predecessor receipt enforcement |
| Scoped verification | One bare `scripts/verify-scoped.sh` batch passed all 7 implicated gates on the relay-complete tree |
| External effects | W04 receipt/closure and draft W05 transition PR #2328; no W05 receipt, W05 closure, publication, or account change |

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
  predecessor. The current formal state is closed/closed/open: W03 and W04 are accepted, and W05 is
  admitted while its own receipt remains pending.
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

1. Require exact-head checks and review clearance, then merge PR #2328 only through
   `scripts/await-pr.sh --merge`.
2. On the actual merged main head, rerun the unchanged live evidence predicate, attach the marked
   PSP-P02-W05 receipt, run `python3 scripts/positioning-program.py --verify-work PSP-P02-W05`, and
   close #2177 only on pass.
3. Hand the accepted W05 main head and W04/W05 marked receipt URLs to the conductor. Do not mutate
   the separately owned W06/W07 or W08 branches from this lane.

## Risks and prohibitions

- W03 and W04 are satisfied. W05 closure remains gated on PR #2328's sanctioned merge plus its
  marked receipt and executable predicate.
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
- W04 integration: https://github.com/organvm/limen/pull/2310 (merged).
- W05 state transition: https://github.com/organvm/limen/pull/2328 (draft until relay-complete
  exact-head verification and review clearance).

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-p02-w04-w05-evidence-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, approval, issue state, or permission.
