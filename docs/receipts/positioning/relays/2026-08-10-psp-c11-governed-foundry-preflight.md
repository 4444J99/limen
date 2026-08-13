---
type: prompt-relay-envelope
version: 3.0
date: 2026-08-12
from: Codex direct-session reversible preflight
to: next authorized PSP-C11 conductor or correctly assigned leaf
scope: /Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees/5a58/limen
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
- Branch: `codex/psp-c11-governed-foundry-preflight`
- Draft PR: https://github.com/organvm/limen/pull/2319
- Conduct state: explicit direct-session reversible preflight; no leaf lease, lifecycle transition,
  completion receipt, or closure claimed

## Verified current state

| Item | Live state |
| --- | --- |
| Pre-integration C11 checkpoint | `db0d991af5bfbfdec19e9fa3b0f5a89d9337e114` |
| Exact source-lock correction head | Pinned in draft PR #2319 because this tracked relay cannot self-name its containing commit |
| Pull request | Draft PR #2319, base `main`; no merge requested or performed |
| Working tree | Clean at the implementation checkpoint; this relay is the only planned subsequent file |
| Program projection | `--check`: 13 chunks, 15 phases, 111 leaves, 127 mapped/projected objects, status `ok` |
| Remote parity | `--verify-remote`: 127 expected / 127 observed / zero missing, orphan, or drift |
| Model assignment parity | `--verify-model-assignments`: all 127 objects valid; C11 Sol/max and all nine leaf pairs unchanged |
| Dependency truth | P02 closed; P04/P11/P12 open; C10 PREPARED at #2321 head `98e10060a31a69c3d6cfe54375c68fe298c6c53a`, not closed |
| C10 integration receipt | Five exact C05/C09 bindings, each `counts_as_closure: false`; deterministic receipt `bcb248826040197de8ef143da48ff61234d2cb2f6d73962fbc424eb2848856e6` |
| C03 checkpoint | Current offer #2312 head `b6af8086c9050634313f519c29a6dfcb922c3721`; W01-W06 formal acceptance remains `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; genuine-reader W07 remains open at #2188 |
| Live ready-work | No C11/P13 leaf is ready |
| Candidate census | Two identical passes: 10 organizations, 317 repositories, 62 candidates, zero new organization/repository/candidate keys |
| Private boundary | 54 public candidate rows, 8 opaque private rows; current full-name and unique-bare-token scan found zero leaks in C11 public paths |
| Demand/readiness | E0 48, E1 9, E2 5; 2 experiment-only, 60 park; 60 diligence-required, 2 archived; 0 transfer-eligible |
| Generated comparison | 62 classifications and 62 non-binding decision records; 54 public comparisons, 8 private classifications withheld, 0 transfer-eligible |
| Synthetic drills | Five operator routes, five access decisions, and five rollback cases passed; invented records only; no simulated human acceptance or external effect; owner custody unchanged |
| Acceptance condition | Preflight met; every formal W01-W09 acceptance and P13 exit predicate remains open |
| Task-specific predicate | Intentionally not run for any leaf because no leaf is ready, leased, or receipt-backed |
| Phase exit proof | Not run; P13 cannot close without all children and an observed transfer or evidence-backed no-go decision |
| External effects | Draft branch/PR only; no contact, send, publication, deploy, DNS, spend, signature, access, transfer, issue close, or merge |

## Exact predicate receipts

The exact containing head and CI state for this source-lock correction are pinned in draft PR #2319.

| Predicate | Result |
| --- | --- |
| `python3 -B scripts/positioning-program.py --check` | pass; 13 chunks, 15 phases, 111 leaves, 127 mapped/projected objects |
| `python3 -B scripts/positioning-program.py --verify-model-assignments` | pass; all 127 assignments valid |
| `python3 -B scripts/positioning-foundry-preflight.py --json` | pass; v2 contract, snapshot, exact dependency heads, C10 source lock, assignments, gates, structures, and drills valid |
| `python3 -B scripts/positioning-foundry-preflight.py --drills --json` | pass; five routing cases, five access cases, exact non-closing C10 readiness receipt, return/governance replay, zero external effects |
| `python3 -B scripts/positioning-foundry-preflight.py --verify-live-snapshot --json` | pass at 2026-08-12T20:14:01Z; full tracked snapshot match; candidate digest `9829f24cc353b23ab8812c8327905cec66ed4df92095552594b60caaf05bc2ca`; repository digest `330521ea037e8913b40052a62b20192203dc60e3cf0194ed01f097f6a4b7d39c`; leak count 0 |
| `python3 -B scripts/positioning-foundry-handoff.py --json` | pass; 62 classifications, 62 decision records, 54 public comparisons, 8 private classifications withheld, exact C10 integration receipt |
| `python3 -B scripts/positioning-foundry-handoff.py --records --json` | pass; deterministic records digest `d432e5c271504bcc13fd3cb9bbb94e5366549ec1063889ad8c319864aa41864e` |
| `python3 -B scripts/positioning-foundry-handoff.py --drills --json` | pass; five rollback cases, zero external effects, owner custody unchanged |
| Combined focused tests | 28 passed |
| Ruff | pass |
| `scripts/verify-scoped.sh` | passed all 7 implicated gates |
| `git diff --cached --check` | pass before implementation commit |

Do not substitute any `--verify-work` invocation for the non-circular predicates above. They prove
this preflight package, not a leaf completion.

## Completed reversible work

- Refreshed the complete 62-row product-candidate snapshot over the 317-repository live owner-wide denominator.
- Bound merged C02 census/classification inputs at accepted commits without copying private facts.
- Fail-closed the v2 contract on the accepted C03 W01-W06 checkpoint, open W07 reader gate,
  prepared C04-C10 exact heads, C10-not-closed truth, and P02/P04/P11/P12 phase state.
- Exact-bound C10 head `98e10060a31a69c3d6cfe54375c68fe298c6c53a`, its deterministic receipt,
  and all five current C05/C09 inputs without promoting any prepared source to closure.
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
  base plus handoff focused suite now contains 28 tests.
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

1. Refresh live registry, exact PR heads, and C11 readiness. Do not assume this relay remains
   current.
2. Wait for the formal dependency graph to expose a leaf as ready; predecessor openness blocks
   closure but not continued reversible, non-duplicative preparation.
3. Start the leaf in a fresh Codex task using the exact model/effort from its live issue, configure
   and register the conduct broker, obtain a lease, and honor that leaf repository/path/effect scope.
4. Integrate only the exact merged C02 census/classification receipts. Re-run the two-pass live
   inventory and privacy scan; never copy private facts into Limen, the PR, or an issue comment.
5. Run the leaf-specific non-circular predicate, attach a structured receipt, and only then run
   `python3 scripts/positioning-program.py --verify-work <WORK-ID>`.
6. For W08, stop before recruitment, terms, signature, access, or transfer unless the exact human
   gates are durably satisfied. A design or synthetic drill is never an observed pilot.

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
- C11 draft PR: https://github.com/organvm/limen/pull/2319

The fresh-agent injection phrase is:

```text
Continue from relay at /Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees/5a58/limen/docs/receipts/positioning/relays/2026-08-10-psp-c11-governed-foundry-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must repeat live orientation and obtain its own identity and authority. This relay
transfers context, not a lease, human approval, legal review, operator acceptance, or permission to
perform an external act.
