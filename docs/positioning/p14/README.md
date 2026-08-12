# PSP-P14 return-loop preflight

This directory documents the reversible control plane for `PSP-C12` / `PSP-P14`. The executable
contract is [`institutio/positioning/p14/control-plane.json`](../../../institutio/positioning/p14/control-plane.json),
the full dependency snapshot is
[`institutio/positioning/p14/dependency-ledger.json`](../../../institutio/positioning/p14/dependency-ledger.json),
and the read-only runner is [`scripts/positioning-p14-control-plane.py`](../../../scripts/positioning-p14-control-plane.py).

This is a preflight, not a completion receipt. It defines the event/KPI dictionary, the weekly,
monthly, and quarterly review contracts, synthetic claim and release drills, the sales and delivery
return paths, portfolio reclassification, and the two-pass comparison. It deliberately cannot
close a P14 leaf, prove demand, prove a client or operator outcome, complete a time-based review
cycle, resolve a human gate, or reach Omega.

## Bounded execution

The runner is offline and deterministic. It reads tracked JSON, emits JSON, and executes no child
commands. In particular, its predecessor policy is `receipt-only`: a current passing predecessor
receipt may be reused as an input, but the runner never invokes a predecessor predicate just to
accumulate another green result.

```bash
python3 scripts/positioning-p14-control-plane.py --check
python3 scripts/positioning-p14-control-plane.py \
  --run-fixture cli/tests/fixtures/positioning-p14/synthetic-cycle.json
python3 scripts/positioning-p14-control-plane.py --preflight
```

`--preflight` exits zero only when the contract and synthetic mechanisms are valid and the live
terminal result still fails truthfully on the absent external receipts. A green preflight therefore
means “the scaffold is ready and honest,” never “P14 is done.”

The v2 preflight distinguishes two independent facts for every upstream chunk: `preflight_state`
records reversible preparation, while `closure_state` records formal lifecycle truth. Every
prepared row also says `counts_as_closure: false`. The ledger is checked against the canonical
registry for chunk dependencies, phase ownership, conductors, all nine P14 model/effort
assignments, issue URLs, and all 23 terminal requirement nodes.

At the 2026-08-12 reconciliation point, all nine C03-C11 predecessor chunks remain formal blockers
and all 23 P14 terminal nodes remain open: 32 blockers, derived rather than hard-coded. The first
execution frontier is `PSP-P03-W07` / issue
[#2188](https://github.com/organvm/limen/issues/2188), assigned to `gpt-5.4-mini` / `low`. Its
five-reader acceptance boundary requires genuine independent target-like readers; model, author,
coached, or fabricated responses do not count.

The live terminal predicate is separate:

```bash
python3 scripts/positioning-p14-control-plane.py --terminal
```

Until a live evidence envelope exists at
`docs/receipts/positioning/p14/live-evidence.json`, the command exits `3` and prints every missing
outcome with its P14 work ID, durable owner, required evidence, and observed deficiency. It never
turns absence into a skip or a synthetic pass.

The public evidence envelope is key-denylisted recursively and permits only opaque identities. A
contact, client, operator, private-repository, price, credential, token, secret, email, or phone
field blocks terminal status wherever it appears. Private evidence bodies remain in their private
owners; the public envelope holds only opaque IDs, aggregates, exact commits, predicates, and HTTPS
receipts.

## Event and KPI contract

Events carry an opaque `event_id`, a declared type, an opaque entity ID, an RFC3339 observation
time, and a scope. The dictionary binds each type to a source, cadence, owner, privacy boundary, and
decision use. It contains no contact details or client/operator identities.

Every metric is a named numerator event divided by a named denominator event. The contract refuses
zero or undeclared denominators, assigns an owner and cadence, and records the decision the metric
may inform plus the inference it may not support.

| Metric | Decision use | Guardrail |
|---|---|---|
| Claim currency | Quarantine stale material claims | The aggregate cannot hide a failed named claim |
| Surface health | Repair or roll back an unhealthy surface | Every named surface remains independently visible |
| Qualified demand | Revisit targeting after the declared threshold | Synthetic or spam events never count |
| Offer conversion | Keep, narrow, promote, or withdraw an offer | Acceptance is not revenue or client-outcome proof |
| Delivery outcome coverage | Block proof promotion when a closeout lacks an outcome | Coverage does not imply a positive result |
| Operator outcome coverage | Route observed results and no-go receipts into classification | A no-go is evidence, not success |
| Claim correction recovery | Keep generation disabled until correction or withdrawal | Quarantine precedes correction and republication |
| Release recovery | Stop releases when exact restoration fails | Health and capture continuity must both pass |
| Portfolio evidence coverage | Lower prominence where evidence is insufficient | Repository volume is not quality |

## Review contracts

The fixture validates the shape of each review but records zero live cycles.

| Review | Minimum terminal evidence | Required decision output |
|---|---:|---|
| Weekly | Four consecutive live receipts | Decision, owner, next predicate, routed packet IDs |
| Monthly | Two consecutive live receipts | Truth/surface/privacy verdict and owned corrections |
| Quarterly | One live receipt covering conversation, funnel, delivery, and claim evidence | Keep/narrow/promote/withdraw, truth-versus-prominence finding, next experiment |

Synthetic review generation cannot advance these counters. Calendar time alone cannot either: each
receipt must contain the named inputs, decision, owner, and durable evidence URL.

## Correction and recovery drills

The claim fixture begins with one claim on two dependent surfaces. The runner removes it from every
dependency, records the regeneration block, accepts only a new `verified` evidence version, and
restores the corrected claim only to the previously affected surfaces. This proves the mechanism;
it does not assert that a real claim incident occurred.

The release fixture records a known-green ID, a distinct bad ID, the exact restored ID, every health
check, the resolved synthetic repository set, and capture ownership before and after. Restoration
must equal the known-green ID and capture ownership must not change. A live W06 receipt still needs
the concrete public-surface repositories and exact predicate-tested heads.

## Feedback and reclassification

The sales fixture crosses a synthetic revision threshold, preserves every outcome ID, and produces
a versioned offer decision. Its price gate stays `pending`, and the output says
`real_demand_claimed: false`.

The delivery fixture maps one synthetic delivery result and one synthetic operator no-go to claim,
classification, and proof impacts. `none` is a valid explicit impact; omission is not. Each outcome
keeps its immutable source receipt, and portfolio changes preserve before/after classes and a
reason. The fixture says both `real_delivery_claimed: false` and
`real_operator_outcome_claimed: false`.

`HG-PRICE-ANCHORS` has one durable human owner:
`his-hand-levers.json -> L-PSP-PRICE-ANCHORS`. The lever remains open until the real W07 outcome
threshold exists. This preflight neither chooses a price nor asks for the decision early.

## Two unchanged passes

The pair envelope contains exactly two `limen.positioning_omega_pass.v1` records. They must be
separate pass numbers with strictly increasing RFC3339 observation times and the same SHA-256 state
digest. A live pass must also preserve the canonical clean result: `ok: true`, exact green parity,
no open IDs, no failures, and a positive verified-receipt count. The live pair binds exactly two
unique HTTPS pass receipts. The verifier rejects a copied/reversed timestamp, changed digest,
wrong pass number, wrong schema, incomplete parity, duplicate receipt URL, or synthetic pair
presented as live.

The synthetic pair exercises comparison only. Terminal Omega still requires the canonical live
command and its durable receipt:

```bash
python3 scripts/positioning-program.py --omega --require-two-pass
```

Its durable program receipt additionally records the exact observed repository head, the consumed
state digest, RFC3339 observation time, and output SHA-256. The digest must equal the verified pair,
and the program observation cannot predate pass two.

## Terminal evidence boundary

The terminal report fails closed until all of these are present:

- current durable work receipts for `PSP-P14-W01` through `PSP-P14-W09`;
- four weekly, two monthly, and one quarterly live review receipts;
- durable claim-quarantine and multi-repository release-recovery drill receipts;
- five qualified real demand outcomes, a live offer decision preserving them, and either one
  paid-audit receipt or five documented no outcomes;
- the resolved `HG-PRICE-ANCHORS` owner receipt;
- at least one real delivery outcome and one observed operator result or evidence-backed no-go;
- the corresponding portfolio impact receipt;
- two unchanged live Omega passes; and
- a passing receipt for the canonical program Omega command.

The actual machine-readable list lives in the control-plane manifest so the predicate and this
description cannot drift into separate acceptance definitions.

## Authority and rollback

The runner has no network or subprocess effect. It does not write `tasks.yaml`, issues, receipts,
claims, surfaces, releases, deployments, accounts, or human decisions. Removing the new P14-owned
paths fully rolls back the preflight; no external state needs reversal. Once live evidence exists,
the owning leaf predicates and the canonical positioning program remain authoritative over this
scaffold.
