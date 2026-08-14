---
type: prompt-relay-envelope
version: 3.0
date: 2026-08-14
from: Codex PSP-P13-W01 formalization correction
to: existing PSP-P13-W01 owner and PSP root conductor
scope: .
phase: PROVE
compression_level: medium
---

# Relay — PSP-C11: governed-foundry handoff preflight

## Routing

- Program scope: `PSP-C11`, `PSP-P13`, and `PSP-P13-W01` through `PSP-P13-W09`
- Root issue: https://github.com/organvm/limen/issues/2157
- Phase issue: https://github.com/organvm/limen/issues/2264
- Leaf issues: https://github.com/organvm/limen/issues/2265 through
  https://github.com/organvm/limen/issues/2273
- Target repository for this preflight: `organvm/limen`
- Future leaf targets: use each live issue target; the collaboration-platform and selected-product
  repositories were not changed by this preflight
- Existing owner task: `019fed3c-88e3-7771-b433-7f46fceedef6`
- Branch: `codex/psp-c11-governed-foundry-preflight`
- Original preflight PR: https://github.com/organvm/limen/pull/2319 (merged)
- Active correction PR: https://github.com/organvm/limen/pull/2418
- Conduct state: the existing owner lane is active for `PSP-P13-W01`; formal completion remains
  pending the sanctioned merge, marked leaf receipt, passing work predicate, and truthful issue
  closure

## Verified current state

| Item | Live state |
| --- | --- |
| Exact correction head | Pinned in active PR #2418 because this tracked relay cannot self-name its containing commit |
| Pull request | PR #2418 is the only active correction lane; merge is permitted only through `scripts/await-pr.sh` after exact-head checks and review are clean |
| Control-plane dependency | PR #2386 merged at main `3cec3399879c9417bcc7639cfcd358ddbc66bc10`; exact work dependencies now admit ready leaves without weakening aggregate phase/chunk closeout order |
| Live ready-work | `PSP-P13-W01` is registry-ready with issue #2265 open; no marked completion receipt is present yet |
| Candidate census | Two identical passes: 10 organizations, 319 repositories, 62 candidates, zero new organization/repository/candidate keys |
| Private boundary | 54 public candidate rows, 8 opaque private rows; current full-name and unique-bare-token scan found zero leaks in C11 public paths |
| Demand/readiness | E0 48, E1 9, E2 5; 2 experiment-only, 60 park; 53 diligence-required, 1 park/archived, 8 private-evidence-withheld; 0 transfer-eligible |
| Generated comparison | 62 classifications and 62 non-binding decision records; 54 public comparisons, 8 private classifications withheld, 0 transfer-eligible |
| Synthetic drills | Five operator routes, five access decisions, and five rollback cases passed; invented records only; no simulated human acceptance or external effect; owner custody unchanged |
| Acceptance condition | The correction package is ready for exact-head review and sanctioned integration; W01 remains formally incomplete until its marked receipt and predicate pass |
| Task-specific predicate | `--verify-work PSP-P13-W01` remains intentionally pending the accepted merge and marked receipt; it is not a substitute for the non-circular predicates below |
| Phase exit proof | Not run; P13 cannot close until all children and its aggregate phase predicate are receipt-valid |
| External effects | Correction branch/PR only so far; no contact, send, publication, deploy, DNS, spend, signature, access, transfer, issue close, or merge |

## Exact predicate receipts

The exact containing head and CI state for this formalization correction are pinned in PR #2418.

| Predicate | Result |
| --- | --- |
| `python3 -B scripts/positioning-foundry-preflight.py --json` | pass; v3 contract, snapshot, exact source/integrated dependency heads, C10 source lock, runtime assignment requirements, gates, structures, and drills valid |
| `python3 -B scripts/positioning-foundry-preflight.py --drills --json` | pass; five routing cases, five access cases, exact non-closing C10 readiness receipt, return/governance replay, zero external effects |
| `python3 -B scripts/positioning-foundry-preflight.py --live --verify-live-snapshot --json` | pass observed at 2026-08-14T16:37:44.371084Z against tracked snapshot captured at 2026-08-14T15:58:07.099488Z; 10 organizations, 319 repositories, 62 candidates; candidate digest `9829f24cc353b23ab8812c8327905cec66ed4df92095552594b60caaf05bc2ca`; repository digest `a002b3f02d0455168dece9f767a2042e2c7d34510e3d700c98e2bfcbe46c22c8`; 84 private repositories scanned and leak count 0 after tracked projection reconciliation |
| `python3 -B scripts/positioning-foundry-handoff.py --json` | pass; 62 classifications, 62 decision records, 54 public comparisons, 8 private classifications withheld, exact C10 integration receipt |
| `python3 -B scripts/positioning-foundry-handoff.py --records --json` | pass; deterministic records digest `305f3833c42c966a8a62c84900ac7c3901d70f4b26f86c01fde91932c47f855c` |
| `python3 -B scripts/positioning-foundry-handoff.py --drills --json` | pass; five rollback cases, zero external effects, owner custody unchanged |
| Combined focused tests | 38 passed |
| Ruff | pass |
| `scripts/verify-scoped.sh` | passed all 7 implicated gates |
| Diff hygiene | pass before the correction commit |

Do not substitute any `--verify-work` invocation for the non-circular predicates above. They prove
this preflight package, not a leaf completion.

## Completed reversible work

- Refreshed the complete 62-row product-candidate snapshot over the 319-repository live owner-wide denominator.
- Bound merged C02 census/classification inputs at accepted commits without copying private facts.
- Fail-closed the v3 contract on the accepted C03 W01-W06 checkpoint, open W07 reader gate,
  C04-C10 exact source/integrated-main heads, C10-not-closed truth, and P02/P04/P11/P12 phase state.
- Exact-bound C10 source `71a6046c2186b4d4ead5136920b82b412ff5d540`, integrated main
  `f45fa5f5952a9ae4a5806a5ac4b3f562ace262e2`, its deterministic receipt, and all five current
  C05/C09 source/integrated pairs without promoting any prepared source to closure.
- Added per-candidate demand evidence/zero-evidence state, next experiment, stop condition,
  conservative readiness/custody screen, economics hypothesis, and transfer blockers.
- Added the operator profile/scorecard, diligence checklist, economics and transfer floors,
  park/kill rules, five structure/return options, staged access pipeline, blank bounded-pilot
  charter, telemetry/cadence, return workflow, and institutional review templates.
- Reapplied the accepted C02 taxonomy to every public candidate while withholding all private
  classification detail.
- Generated one deterministic, non-binding decision record per candidate with evidence,
  readiness, economics, no-go codes, next action, gates, and owner custody unchanged.
- Added exact authority and private-evidence contracts that deny contact, disclosure, credentials,
  terms, spend, publication, deployment, and transfer during preflight.
- Added five executable rollback cases covering evidence, security, custody, operator, and
  downside-economics failures with zero external effects.
- Retained the base validator and synthetic operator/access/return/governance drills; the combined
  base plus handoff focused suite now contains 38 tests, including duplicate-member and surplus-root
  fail-closed cases for both public contracts.
- Made live snapshot writes fail closed when paired with synthetic drills, and required tracked
  snapshot validation even when a live verification run also writes a candidate refresh.
- Restricted snapshot sources to the two accepted C02 inventory inputs; the P02 closure receipt is
  dependency evidence, not candidate data.

## Decisions and rationale

| Decision | Evidence and rationale |
| --- | --- |
| Public names, opaque private rows | Limen is public. Full live facts are inspected in memory; the public package preserves the complete denominator without exposing private identities. |
| Metadata demand cap 35 | Stars, forks, and watchers are discovery signals only. They cannot establish adoption, buying intent, revenue, or transfer readiness. |
| Missing readiness evidence scores zero | Repository metadata cannot prove build, test, deploy, security, data, IP, observability, return, or maintenance readiness. |
| No selected structure or candidate | Legal/economic selection and real operator state require predecessor evidence plus the named human gates. |
| Preflight in Limen only | W04/W06/W07 target another repository when ready. Staging the shared public-safe contract here avoids an unleased cross-repository mutation or duplicated active lane. |
| Every candidate non-transferable | No E3+ demand receipt, full diligence, scored real operator, approved terms, or observed pilot exists. A truthful zero is the current result. |

## Next actions

1. Re-query PR #2418 and issue #2265. Require the exact remote head, clean merge state, green
   required checks, and zero unresolved review threads.
2. Merge only through `scripts/await-pr.sh 2418 --repo organvm/limen --merge`; do not use a direct,
   admin, force, or bypass merge.
3. On the accepted main head, re-run the non-circular foundry predicates and preserve the private
   boundary; never copy private facts into Limen, the PR, or an issue comment.
4. Attach the marked structured receipt for `PSP-P13-W01`, run
   `python3 scripts/positioning-program.py --verify-work PSP-P13-W01`, and close #2265 only when it
   passes. Run the same predicate after closure to prove terminal issue state.
5. Return the accepted main head, marked receipt URL, and passing predicate to the PSP root
   conductor. Leave P13 aggregate closure to its owning conductor.

## Human gates and prohibitions

The canonical gate definitions remain in `institutio/positioning/program.yaml`; this relay does not
create a competing registry.

- `HG-PUBLICATION-SEND`: unpulled; no recruiting or outreach send.
- `HG-OPERATOR-TERMS`: unpulled; no license, equity, revenue-share, custody, access, or transfer
  terms selected or approved.
- `HG-CONTRACT`: unpulled; no signature, spend, liability, data-processing, or service commitment.

Private repository identities and private economics remain outside this public relay. Do not touch
`tasks.yaml`, sibling worktrees, shared generated indexes, main, DNS, deployment, accounts, or issue
state from this handoff.

## References

- C11 package:
  `docs/positioning/foundry/psp-c11/README.md`
- Machine contract:
  `docs/positioning/foundry/psp-c11/foundry-preflight-contract.json`
- Candidate snapshot:
  `docs/positioning/foundry/psp-c11/product-candidate-snapshot.json`
- Synthetic receipt:
  `docs/positioning/foundry/psp-c11/synthetic-drill-receipt.json`
- P02 closure: https://github.com/organvm/limen/issues/2172
- C02 census accepted merge: https://github.com/organvm/limen/pull/2305 at
  `10cf8476d5e88309c71d5fac25167ec7b7af59c4`
- C02 classification accepted merge: https://github.com/organvm/limen/pull/2307 at
  `35134b95650a26185a58eb3b3a82632e5b80b5b2`
- C03 reader gate: https://github.com/organvm/limen/issues/2188
- Original C11 preflight PR: https://github.com/organvm/limen/pull/2319
- Active C11 correction PR: https://github.com/organvm/limen/pull/2418
- P13-W01 work issue: https://github.com/organvm/limen/issues/2265

The fresh-agent injection phrase is:

```text
Continue the existing PSP-P13-W01 owner lane from `docs/receipts/positioning/relays/2026-08-10-psp-c11-governed-foundry-preflight.md`. Re-query PR #2418 and issue #2265, then follow Next Actions without creating a duplicate task or PR.
```

The receiver must repeat live orientation and preserve the existing owner/task identity. This relay
transfers context, not legal review, operator acceptance, or permission to perform any external act
beyond the already authorized repository integration and receipt workflow.
