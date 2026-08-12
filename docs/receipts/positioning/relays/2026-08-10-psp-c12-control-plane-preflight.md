---
type: prompt-relay-envelope
version: 2.0
date: 2026-08-12
from: Codex direct-session reversible preflight
to: next authorized PSP-C12 conductor
scope: organvm/limen branch codex/psp-c12-control-plane-preflight
phase: PROVE
compression_level: high
---

# Relay — PSP-C12 dependency and Omega control-plane preflight

## Routing and truth boundary

- Program scope: `PSP-C12`, `PSP-P14`, and `PSP-P14-W01` through `PSP-P14-W09`
- Parent issue: [#2274](https://github.com/organvm/limen/issues/2274)
- Leaf issues: [#2275](https://github.com/organvm/limen/issues/2275) through
  [#2283](https://github.com/organvm/limen/issues/2283)
- Branch: `codex/psp-c12-control-plane-preflight`
- Draft PR: [#2320](https://github.com/organvm/limen/pull/2320)
- Exact predicate-tested implementation head: `8a9a7af246af27eba807552e2332c66bb691ec1a`
- State: **PREPARED/PREFLIGHT**
- Formal leaf receipts, phase proof, root proof, and closure: not run or claimed
- External effects: draft branch and PR metadata only

This lane has no authority to convert preparation into closure, invent external outcomes, solicit
readers, choose a visual direction, send, publish, deploy, sign, spend, or mutate accounts.

## Dependency truth and execution frontier

The v2 control plane validates a full tracked dependency ledger against the canonical program
registry. `preflight_state` and `closure_state` are independent, and every prepared row says
`counts_as_closure: false`.

- P02 is closed at accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7`.
- Nine predecessor chunks, C03 through C11, remain formal blockers.
- C03 is accepted through W06 at `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`.
- The exact first frontier is `PSP-P03-W07` / [#2188](https://github.com/organvm/limen/issues/2188),
  assigned `gpt-5.4-mini` / `low`.
- W07 requires five genuine independent target-like readers. Model, author, coached, or fabricated
  responses do not count; this preflight performed no outreach.
- C04-C11 reversible drafts are bound at their current exact PR heads. C11 is now
  [#2319](https://github.com/organvm/limen/pull/2319) head
  `92325b04eb741f63a7013bf33d6900568fbef185`.
- C06 still has exactly three Product Design directions; all remain **UNSELECTED**.
- All 23 P14 terminal requirement nodes remain open.
- Derived current blocker total: 9 predecessor chunks + 23 P14 requirements = **32**.

The ledger validates phase ownership, chunk dependencies, chunk conductors, all nine P14 issue
URLs, full work dependencies, and exact model/effort assignments. A registry drift fails closed.

## What the v2 control plane proves

- The event/KPI, review, claim-incident, release-recovery, sales-feedback, delivery-feedback, and
  synthetic two-pass mechanisms are internally coherent and execute no predecessor commands.
- Public evidence is recursively key-denylisted. Contact/client/operator names, private repository
  names, price amounts, credentials, authorization, tokens, secrets, email, phone, and private
  evidence bodies block terminal status wherever they occur.
- Live Omega requires two strictly ordered canonical passes with one digest, clean 127-object
  parity, no open IDs, no failures, positive verified-receipt counts, and two unique HTTPS pass
  receipts.
- The consuming program receipt must bind the same state digest, an exact observed repository head,
  RFC3339 observation time at or after pass two, output SHA-256, and the canonical command.
- Synthetic results remain explicitly unusable for Omega, demand, client/operator outcomes,
  time-based review completion, or human acceptance.

## Exact predicate receipts

| Predicate | Result |
|---|---|
| `python3 -B scripts/positioning-program.py --check` | PASS; 13 chunks, 15 phases, 111 leaves, 127 mapped/projected objects |
| `python3 -B scripts/positioning-program.py --verify-model-assignments` | PASS; all 127 assignments valid |
| `python3 -B scripts/positioning-p14-control-plane.py --check` | PASS; v2 contract, 9 predecessor chunks, 23 terminal nodes, exact W07 frontier |
| synthetic fixture | PASS; no predecessor command or external effect |
| `python3 -B scripts/positioning-p14-control-plane.py --preflight` | PASS; terminal truth blocked on exactly 32 current atoms |
| `python3 -B scripts/positioning-p14-control-plane.py --terminal` | expected exit 3; 9 predecessor blockers + 23 P14 requirements |
| focused pytest | 17 passed |
| Ruff lint and format | PASS |
| scoped cheap wave | PASS; 13 implicated gates |
| scoped serialized CLI suite | 5705 passed, 2 skipped; 2 unrelated process-timing tests failed in `test_campaign_relay_effector.py` |

The two heavy-suite failures did not touch P14 code or assertions: one fixture did not create its
provider PID file before assertion, and one timeout fixture did not create its child PID file. The
unchanged heavy suite was not replayed for reassurance. Draft-PR CI on the superseding exact head is
the next independent integration receipt.

## Activation and completion predicates

1. Re-read the registry and dependency ledger; do not infer readiness from this dated relay.
2. Do not create a duplicate lane. Continue the existing chunk/PR and activate only the exact
   frontier admitted by live state.
3. `PSP-P03-W07` remains the first frontier until five genuine-reader receipts satisfy its predicate and
   the owning C03 lane closes it correctly.
4. Populate `docs/receipts/positioning/p14/live-evidence.json` only from durable owner receipts.
   Private bodies remain in private ledgers; the public envelope carries opaque IDs, aggregates,
   exact commits, predicates, and HTTPS receipts.
5. P14 terminal predicate: `python3 scripts/positioning-p14-control-plane.py --terminal` exits 0.
6. Program terminal predicate: `python3 scripts/positioning-program.py --omega --require-two-pass`
   exits 0 against two distinct unchanged live observations.

## Human gates and prohibitions

- `HG-PRICE-ANCHORS` remains unpulled; do not choose or claim a price decision.
- Reader outreach, publication, and direct-message sends remain behind their exact authority.
- Visual selection/build remains with Product Design; all three directions remain unselected.
- No merge, issue closure, send, publication, deployment, DNS, spend, signature, account mutation,
  private-evidence exposure, or task-board edit occurred.

## Durable owners

- Control contract: `institutio/positioning/p14/control-plane.json`
- Dependency ledger: `institutio/positioning/p14/dependency-ledger.json`
- Runner: `scripts/positioning-p14-control-plane.py`
- Operator guide: `docs/positioning/p14/README.md`
- Synthetic fixture: `cli/tests/fixtures/positioning-p14/synthetic-cycle.json`
- Draft PR: [#2320](https://github.com/organvm/limen/pull/2320)

The receiver must verify live state and obtain its own authority. This relay transfers context, not
identity, lease, approval, consent, acceptance, external evidence, or closure.
