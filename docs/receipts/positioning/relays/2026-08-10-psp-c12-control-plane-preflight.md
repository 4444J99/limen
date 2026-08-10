---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex direct-session PSP-C12 preflight
to: next healthy PSP-C12 conductor
scope: organvm/limen branch codex/psp-c12-control-plane-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-C12: reversible P14 control-plane preflight

This is a public-safe relay. Local absolute paths, private ledgers, identities, and outcome content
are intentionally omitted; the receiver resolves this tracked path inside a fresh worktree.

## Routing

- Program work IDs: `PSP-P14-W01` through `PSP-P14-W09` (preflight only; none closed here)
- Parent issue: <https://github.com/organvm/limen/issues/2274>
- Leaf issues: <https://github.com/organvm/limen/issues/2275> through
  <https://github.com/organvm/limen/issues/2283>
- Target repository: `organvm/limen`
- Branch: `codex/psp-c12-control-plane-preflight`
- Draft PR: <https://github.com/organvm/limen/pull/2320>
- Predicate-tested implementation commit: `1c6f1a17c74ddc22a457eab0bdd37fba5259502e`
- Tested base observation: `b9c6872cbe352b64e37c69a7133f43f7d61018b5`
- Conduct root/run/lease: none. The broker bootstrap was attempted once and was not configured in
  this task environment, so no child agent or P14 leaf was claimed. This direct-session lane staged
  only the explicitly authorized non-closing preflight.

## Verified current state

| Item | Live state |
|---|---|
| Exact predicate-tested head | `1c6f1a17c74ddc22a457eab0bdd37fba5259502e` |
| Exact remote branch head at relay authoring | `1c6f1a17c74ddc22a457eab0bdd37fba5259502e` |
| Working tree | Clean at the implementation commit before adding this relay; the relay is the only successor change |
| Acceptance condition | Preflight met; every P14 leaf and phase/root terminal condition remains open |
| Task-specific predicate | `python3 scripts/positioning-p14-control-plane.py --preflight` exited `0`: contract valid, synthetic fixture pass, zero predecessor commands executed, terminal blocked on 23 named live outcomes |
| Focused tests | `python3 -m pytest -q cli/tests/test_positioning_p14_control_plane.py` — 11 passed in 0.05s |
| Terminal observation | `python3 scripts/positioning-p14-control-plane.py --terminal` exited expected `3`, `status=blocked`, `missing_count=23` |
| Scoped repository gate | Cheap wave passed. Heavy wave was not admitted because of live swap pressure and returned the bounded exit `75`; required draft-PR CI remains authoritative for that wave |
| Receipt verifier | No P14 leaf receipt was minted and no `--verify-work PSP-P14-*` command was run |
| Phase exit proof | Not run; P14 children and live outcome gates are not complete |
| Omega observation | Synthetic pair comparison only. No live Omega pass file was emitted or claimed |
| External effects | Branch push and requested draft PR only; no send, publication, deployment, DNS, spend, signature, account, or issue-state mutation |

## Completed work

- Added the P14-owned event and KPI dictionary with stable sources, denominators, owners, cadence,
  privacy boundaries, decision uses, and guardrails.
- Added machine-checked weekly, monthly, and quarterly review contracts that reject synthetic
  fixtures as completed live cycles.
- Added deterministic synthetic claim quarantine/correction, exact release recovery, sales and
  delivery feedback, portfolio impact, and distinct-two-pass fixtures.
- Added an offline terminal predicate that names all 23 missing live outcomes and their owners.
- Reused the current P00-W07 receipt by digest and executed no predecessor command.
- Recorded `HG-PRICE-ANCHORS` once in `his-hand-levers.json` as `L-PSP-PRICE-ANCHORS`, still open.
- Corrected the retired quota lever so historical Agy evidence cannot reappear as a PSP gate;
  merged PR #2300 and the passing P00 receipt remain authoritative.
- Preserved every canonical leaf model/effort assignment; no program manifest assignment or
  generated PSP index changed.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Stage a chunk-level preflight without leaf claims | Live `--ready --json` contained no P14 leaf, while the direct request explicitly authorized reversible downstream preparation without closure |
| Keep predecessor handling receipt-only | The exact P00-W07 receipt already passes; replay would add cost without new evidence |
| Separate preflight success from terminal success | A green scaffold must not be convertible into an Omega, demand, client, operator, cadence, or human-acceptance claim |
| Keep the PR draft | The formal DAG, live receipts, required time windows, real outcomes, and host-admitted heavy/CI verification are not complete |

## Next actions

1. Review draft PR #2320 and consume its CI result at the exact branch head; do not merge from this
   relay and do not rewrite the predicate-tested implementation commit merely because `main` moves.
2. Re-run `python3 scripts/positioning-program.py --ready --json`. Execute a P14 leaf only when it
   is live-ready, using its exact registry model/effort pair and a fresh broker lease. The obsolete
   provider-diversity/Agy gate must not be restored.
3. Populate `docs/receipts/positioning/p14/live-evidence.json` only from durable owner receipts.
   Private outcome bodies remain in their private ledgers; the public envelope carries opaque IDs,
   exact heads, counts, predicates, and HTTPS receipts only.
4. Re-run `python3 scripts/positioning-p14-control-plane.py --terminal`. Only an exit `0` permits
   the canonical live `python3 scripts/positioning-program.py --omega --require-two-pass` step.

## Completion and switch predicates

- One-line launch command: `python3 scripts/positioning-p14-control-plane.py --preflight`
- Switch-to-leaf predicate: `python3 scripts/positioning-program.py --ready --json` includes a
  `PSP-P14-W*` row and the conductor can obtain its exact broker lease.
- P14 terminal predicate: `python3 scripts/positioning-p14-control-plane.py --terminal` exits `0`.
- Program terminal predicate: `python3 scripts/positioning-program.py --omega --require-two-pass`
  exits `0` against two distinct unchanged live observations.

## Risks and prohibitions

- Human gate still unpulled: `his-hand-levers.json -> L-PSP-PRICE-ANCHORS`; do not surface it before
  the real W07 outcome threshold exists and do not infer a decision.
- Sensitive/private boundary: no contact identity, client/operator identity, private evidence body,
  price value, or private repository name belongs in the public evidence envelope.
- Do not edit `tasks.yaml`, shared generated PSP indexes, or issue states from this relay.
- Do not merge, force-push, write `main`, send, publish, deploy, change DNS, spend, sign, or mutate an
  account.
- Rollback route: revert the draft PR. The runner has no network/subprocess effect and created no
  external state beyond the branch and draft PR.

## References

- Control contract: `institutio/positioning/p14/control-plane.json`
- Runner: `scripts/positioning-p14-control-plane.py`
- Operator guide: `docs/positioning/p14/README.md`
- Synthetic fixture: `cli/tests/fixtures/positioning-p14/synthetic-cycle.json`
- Draft PR: <https://github.com/organvm/limen/pull/2320>

The fresh-agent injection phrase is:

```text
Continue from relay at <fresh-worktree>/docs/receipts/positioning/relays/2026-08-10-psp-c12-control-plane-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must resolve the tracked path locally, verify live state, and obtain its own authority.
This file transfers context, not identity, lease, approval, or permission.
