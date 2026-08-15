# s11 — fleet completion: the bar binds every lane, and every measure states its population

## The defect

A five-lane insights sweep on 2026-08-15 (Claude `/insights` plus `vendor-insights` over codex,
copilot, opencode, antigravity) found **one defect wearing five costumes**. Claude declares COMPLETE
early. Codex never declares done — nineteen capsules, each answering "are we there yet" with a
bigger plan. Opencode truncates mid-survey with no receipt: 134 tool calls, one PR merged of ~130
candidates. Antigravity dies on provider quota mid-fan-out. Copilot — which produces the best
finished artifacts in the corpus — truncates mid-closeout.

In every case the work landed and **the proof did not**.

## What exploration actually found

Not missing machinery. Machinery that lands green and never fires:

| Organ | State when measured |
|---|---|
| `worktree-debt.py --fail-on-debt` | implements the exact-zero completion bar; **zero non-doc callers** |
| `orphan-watchers.py --check` | beat- and SessionEnd-wired; absent from the interactive closeout path |
| `no-tasks-on-me.sh` | the named closeout gate; read **no working-tree state at all** |
| SessionEnd model guard | invoked with `--max-billable-tokens 999999999` |
| beat `fable-balance` audit | gated on a parameter **exported by nothing**; had never run once |
| `closeout-reconcile` sensor | `default: "0"`, arming lever open |
| `insight-cross-vendor` | refreshes 11 lane indexes every 24h; **all 11 "never narrated"** |

The estate names this itself in `spec/armed-valves.json`: *"An unarmed guard is byte-identical to a
guard that ran and found nothing."*

## The two invariants this stream owns

1. **The completion bar is executable, and it binds every lane.** Not prose in one instruction file
   that one vendor reads. A rule written for the fleet is implemented over the fleet's *registry* —
   otherwise the lanes it was never written for are exempt by accident, and the exemption is
   invisible exactly where it matters. Precedent:
   `PREC-2026-08-15-lane-scoped-rule-exempts-every-other-lane`.

2. **Every measure states its population.** A predicate that passes over an empty or partial
   population is indistinguishable from one that checked and found nothing. Buckets sum to a
   *declared* denominator; the residual is fatal, never advisory; a claimed bound needs measured
   evidence. Precedent:
   `PREC-2026-08-15-a-loop-with-no-consumer-is-indistinguishable-from-no-measurement`.

## Shipped

- **#2462** — `no-tasks-on-me.sh` §11–13 (own tree clean, branch pushed, no orphan watcher, ≥1
  durable artifact); guards un-neutered; the beat's Fable audit made reachable (5 real violations on
  its first execution); SessionStart states its verifying SHA and whether refs are fresh, and
  declares standing grants; orientation 8.29s → 3.12s, back inside its `timeout 5` hook budget.
- **#2468** — `limen.bucket_partition` (the summing denominator, prose from one lane's dispatch
  brief given an exit code) and `check-reserved-tier.py`, its first consumer: 24 unaccepted
  reserved-tier runs across lanes, over a stated denominator of 132 sessions read of 263 in window.

## Open

- Four lanes record no model identity and are baselined BLIND. Being listed is **not permission** —
  an undetectable violation is worse than a visible one.
- The claims axis is unmeasurable: `reconcile-closeouts.py --check` exits `0` having examined **0
  claims**. Cross-vendor session-claim capture is the next form, after which completion honesty
  earns its own ideal-form row.
- Narration has no mechanical terminus. The beat can refresh indexes; it cannot read them.

## Predicate

`scripts/check-reserved-tier.py` — exit `0` ⟺ no lane ran a reserved tier without a covering
acceptance receipt and no new blindness appeared. Ideal form:
[`IF-FLEET-LEGIBLE`](../../IDEAL-FORMS-LEDGER.md).
