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
- Prior predicate-tested implementation head: `8a9a7af246af27eba807552e2332c66bb691ec1a`
- Live C12 head before this additive patch: `34d9abb3145e8794e7a4602d401af9a09a20a74f`
- Additive v3 implementation commit: `3dc24535d819c7253bc19f5170115439925b8911`
- State: **PREPARED/PREFLIGHT**
- Formal leaf receipts, phase proof, root proof, and closure: not run or claimed
- External effects: draft branch and PR metadata only

This lane has no authority to convert preparation into closure, invent external outcomes, solicit
readers, choose a visual direction, send, publish, deploy, sign, spend, or mutate accounts.

## Dependency truth and two independent frontiers

The v3 control plane validates a full tracked dependency ledger against the canonical program
registry. `formal_execution_frontier` and `reversible_preparation_frontier` are distinct.
An external gate on the formal frontier blocks formal activation/closure only; it must not suppress
independent bounded repository work in later prepared owner lanes. Every prepared row says
`counts_as_closure: false`.

- P02 is closed at accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7`.
- Nine predecessor chunks, C03 through C11, remain formal blockers.
- C03 is accepted through W06 at `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`.
- The formal frontier is `PSP-P03-W07` / [#2188](https://github.com/organvm/limen/issues/2188),
  assigned `gpt-5.4-mini` / `low`.
- W07 requires five genuine independent target-like readers. Model, author, coached, or fabricated
  responses do not count; this preflight performed no outreach.
- C04-C12 remain independently admissible for non-effect repository preparation in their existing
  owner lanes. No owner branch or PR is duplicated by this relay.
- C06 still has exactly three Product Design directions; all remain **UNSELECTED**.
- All 23 P14 terminal requirement nodes remain open.
- Derived current blocker total: 9 predecessor chunks + 23 P14 requirements = **32**.

The ledger validates phase ownership, chunk dependencies, chunk conductors, all nine P14 issue
URLs, full work dependencies, and exact model/effort assignments. A registry drift fails closed.

### Reversible preparation owners observed live on 2026-08-12

| Chunk | Owner PR | Owner branch | Observed head | Closure value |
|---|---:|---|---|---|
| C04 | [#2313](https://github.com/organvm/limen/pull/2313) | `codex/psp-c04-proof-experience-preflight` | `5bf686f6ceba200c6157bd87eb6e5298750a4ffb` | false |
| C05 | [#2315](https://github.com/organvm/limen/pull/2315) | `codex/psp-c05-delivery-os-preflight-relay` | `a72a05d917bf14d53221c7d02ec52d3786b4f88e` | false |
| C06 | [#2317](https://github.com/organvm/limen/pull/2317) | `codex/psp-c06-public-surfaces-relay` | `4eb50463b7f4136b47a103c9792c1ded5caf7873` | false |
| C07 | [#2318](https://github.com/organvm/limen/pull/2318) | `codex/psp-c07-private-inbound-preflight` | `c3b92707a0f6d0ea3076680d100d60d0217f8fe9` | false |
| C08 | [#2316](https://github.com/organvm/limen/pull/2316) | `codex/psp-c08-proof-led-content-preflight` | `ef6e4df64f97c11dba2c159752d5a13b50a96c10` | false |
| C09 | [#2322](https://github.com/organvm/limen/pull/2322) | `codex/psp-c09-qualification-conversion-relay` | `21f3132f129aa6e1eba515f03aa19619533cef4b` | false |
| C10 | [#2321](https://github.com/organvm/limen/pull/2321) | `codex/psp-c10-readiness-preflight` | `620ae2e87131cb871f73b8c0f230d20f9883d85c` | false |
| C11 | [#2319](https://github.com/organvm/limen/pull/2319) | `codex/psp-c11-governed-foundry-preflight` | `db0d991af5bfbfdec19e9fa3b0f5a89d9337e114` | false |
| C12 | [#2320](https://github.com/organvm/limen/pull/2320) | `codex/psp-c12-control-plane-preflight` | runtime exact-head binding | false |

All nine PRs were open drafts when queried. Their existence, heads, green checks, and prepared
artifacts are owner receipts only; none closes a dependency, leaf, phase, or the program.

### P14 model/effort assignments

| Work | Model | Effort |
|---|---|---|
| W01 | `gpt-5.6-terra` | `high` |
| W02 | `gpt-5.6-luna` | `medium` |
| W03 | `gpt-5.6-sol` | `xhigh` |
| W04 | `gpt-5.6-sol` | `max` |
| W05 | `gpt-5.6-terra` | `high` |
| W06 | `gpt-5.6-sol` | `xhigh` |
| W07 | `gpt-5.6-terra` | `high` |
| W08 | `gpt-5.6-terra` | `high` |
| W09 | `gpt-5.6-sol` | `ultra` |

## What the v3 control plane proves

- Typed schemas and deterministic commands now cover KPI collection; weekly, monthly, and quarterly
  review construction; claim quarantine/corrected republication; exact multi-repository release
  recovery; private demand/delivery/operator projection; portfolio impact coverage; evidence
  envelope construction; automatic frontier activation checks; and two unchanged observations.
- Every prepared runner is read-only or synthetic-temporary, executes no predecessor commands, and
  emits `counts_as_closure: false`. Runner output also refuses to self-certify terminal evidence.
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
| `python3 scripts/positioning-p14-control-plane.py --check` | PASS; v3 contract, 13 runners, synthetic operational fixture, formal W07 frontier, and nine C04-C12 reversible owners |
| synthetic fixture | PASS; no predecessor command or external effect |
| `python3 scripts/positioning-p14-control-plane.py --preflight` | PASS; terminal truth blocked on exactly 32 current atoms |
| `python3 scripts/positioning-p14-control-plane.py --terminal` | expected exit 3; 9 predecessor blockers + 23 P14 requirements |
| operational fixture | PASS; W01-W09 runnable, synthetic, non-closing, no predecessor command |
| focused pytest | PASS; 28 tests, including the W07-open/non-empty C04-C12 frontier regression |
| scoped exact-tree batch | New P14 gate PASS; all other selected shards passed except `verify-resolver-test`, which correctly caught its stale registry-change expectation after the new gate was registered |
| invalidated resolver shard | PASS after adding `positioning-p14-control-plane-test` to the expected registry selection; all selection fixtures pass |
| diff hygiene and Ruff | PASS |

The scoped batch was not replayed after the single resolver expectation correction. Its unchanged
green shard receipts were retained; only the invalidated resolver shard and the P14-focused receipt
were rerun, as required by the bounded-composition contract. The relay-only receipt commit that
follows this implementation commit changes no runner, schema, fixture, or frontier truth.

## Activation and completion predicates

1. Re-read the registry and dependency ledger; do not infer readiness from this dated relay.
2. Do not create a duplicate lane. Continue the existing owner branch/PR for each chunk.
3. `PSP-P03-W07` remains the formal lifecycle frontier until five genuine-reader receipts satisfy
   its predicate and the owning C03 lane closes it correctly. This does not suppress independent
   reversible preparation in the C04-C12 owner lanes listed above.
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
- Operations registry and schemas: `institutio/positioning/p14/operations.json` and
  `institutio/positioning/p14/schemas/`
- Runner: `scripts/positioning-p14-control-plane.py`
- Operator guide: `docs/positioning/p14/README.md`
- Synthetic fixture: `cli/tests/fixtures/positioning-p14/synthetic-cycle.json`
- Full operational fixture: `cli/tests/fixtures/positioning-p14/operational-cycle.json`
- Draft PR: [#2320](https://github.com/organvm/limen/pull/2320)

The receiver must verify live state and obtain its own authority. This relay transfers context, not
identity, lease, approval, consent, acceptance, external evidence, or closure.
