# The Salve: reopen the valve, feed the lane, land the value — jules to 100/day

Issue: #1874
PR: #1893

## Context

Operator mandate (already codified 2026-07-23 in `capacity.py:68-75`): jules's 100-task/day quota
must be consumed autonomously — "underuse is a defect." Observed instead: **zero dispatch since
2026-07-19**, board frozen at `spent 8/600` since 2026-07-26, 829 open tasks, 1 stale in-flight.
The daily quota evaporates unused every midnight; nothing compounds.

Exploration (3 agents, verified file:line) found the wire cut in four independent places, plus a
deeper truth: **when dispatch DID run at 90–190/day (June–July), only ~15% completed and 308
jules-authored PRs piled up `lifecycle:blocked` — 23.8% of the estate's 1,293-PR debt.** Raw
saturation compounds debt, not value. The salve is therefore a closed loop, not an open valve.

## Root causes (each verified)

1. **Governor parked**: `logs/autonomy-policy.json` = `mode: observe, dispatch_enabled: false`
   from an expired 2026-07-21 maintenance window. All resume predicates pass
   (`logs/autonomy-maintenance-resume.json`) but nothing ever flips the mode back
   (`scripts/autonomy-governor.py:75-105`; its own comment at :118-127 records the 15-day stall).
2. **No live dispatcher**: the heartbeat daemon contains zero dispatch calls; the only
   `limen dispatch --live` call sites (`metabolize.sh:80-84`, `saturate.sh:68`) have **no caller**
   (baselined: `unreachable-runners-baseline.txt:4`). 41 `source:[metabolize]` sensors never run —
   including `jules-supply` (mints packets, armed by default) and `dispatch-continuity`
   (the starvation alarm itself).
3. **Self-sealing admission gate**: `dispatch_admission_check` exits 20 `stop_no_durable_progress`
   (no value landed in 1.5h) — but nothing can land because dispatch is refused. The budget reset
   sits *after* the admission return (`dispatch.py:5392` vs `:5401`), so the 8/600 corpse never resets.
4. **Candidate starvation**: 738/829 open tasks (89%) fail WorkLoanV1 readiness
   (`work_loan.py:281-312`); jules's 162 open → 21 loan-ready → 8 after the value gate.
5. **Landing gap**: 308 blocked jules PRs, all `classification: owner_route`; `release-stale` is
   jules-scoped so the stale codex claim (`GH-organvm-hospes-9`, stuck since 07-23) never frees;
   down-lane gate reads a fossilized 2026-07-10 "exhausted" receipt.

## Design (two halves, one interlock)

**Valve chain** — `logs/autonomy-policy.json` becomes the SINGLE autonomous-dispatch valve.
`LIMEN_DISPATCH` stays the untouched his-hand lever for manual metabolize/saturate runs. No plist
edits (hook-blocked); jules is a remote lane, so the 16GB host takes no local load.

**Throughput loop** — dispatch volume is clamped to landed volume: cold-start bootstrap 25/day;
full 100/day unlocks only when rolling landed/dispatched ≥ 0.30. The flywheel can spin up but
never outrun its own merge path. Supply organs keep ≥100 loan-ready packets minted; landing organs
drain sessions → PRs → merges with receipts.

## PR sequence (one concern each; merge order as numbered)

**PR-A `feat/throughput-governor`** — the interlock; lands FIRST.
- `cli/src/limen/capacity.py`: `lane_throughput_cap(board, agent)` — bootstrap 25/day when
  `dispatched_3d < 20` (never 0, no self-seal); full target when `landed/dispatched ≥ 0.30`; else
  `max(25, 3×landed)`. Params in `parameters.yaml` (`LIMEN_THROUGHPUT_*`, kill-switch). Plus a
  `lane-balance-jules` blocker row in `capacity_fill_snapshot` (anti-favoritism).
- `cli/src/limen/dispatch.py`: clamp in `_remaining_budget` (:5268 — the chokepoint every engine
  consults) + receipt to `logs/throughput-governor.jsonl` when binding.
- `scripts/lane-throughput.py` gauge + `sensors.yaml` entry (advisory).
- Tests: `cli/tests/test_throughput_governor.py` (cap-never-zero, ramp math, receipt, kill-switch).

**PR-B `feat/owner-route-drain`** — landing capacity for the 308 blocked PRs; the organ that
`GITVS-UNCAPPED-PR-DEBT-0715` [critical] names — dispatch/close that task against it.
- `cli/src/limen/owner_route_drain.py` + `scripts/owner-route-drain.py`: enumerate jules PRs live
  via `gh` (NOT the privacy-redacted debt ledger); classify each into exactly one of
  MERGE (only on `merge-policy.sh` exit 0 — website guardrail stays its verdict) /
  SUPERSEDE / CLOSE / ROUTE-TO-HEAL (defer to `self-heal.py`'s writer). Receipts to
  `logs/owner-route-drain.jsonl`. Dry-run default; `LIMEN_OWNER_ROUTE_DRAIN_APPLY=1` arms;
  `--limit 15`, `--merge-limit 5`. Classification-only under any pause marker (the GITVS task's
  own pause clause). Wire as a guarded step in `drain.sh`.
- Config: `LIMEN_JULES_LAND_LIMIT` 3→5, `LIMEN_MERGE_SCAN` 30→50 (declared in parameters.yaml).
- Tests: `cli/tests/test_owner_route_drain.py` (verdict matrix vs fake gh, merge-only-on-exit-0,
  pause → classify-only, bounds).

**PR-C `fix/autonomy-governor-window-restore`** — the governor auto-heals.
- `scripts/autonomy-governor.py`: `_try_restore_dispatch()` in `current_mode()` — a *finite*
  maintenance window whose declared resume predicate passes flips `observe → dispatch`, moves the
  window to `completed_maintenance_window` (idempotent), writes receipt
  `logs/autonomy-policy-restore.json`. Never flips: indefinite observe (no window),
  `restore: manual`, `AUTONOMY_PAUSED` present, or unwritable policy (fail-closed).
  DEFAULT_POLICY stays observe/false. On first read after merge, the live policy flips itself —
  no manual write.
- Param `LIMEN_AUTONOMY_WINDOW_RESTORE` (default 1). Tests in `cli/tests/test_autonomy_governor.py`.

**PR-D `fix/dispatch-admission-bootstrap`** — break the self-seal.
- `dispatch.py`: move `_reset_budget_if_needed` + persist ABOVE the admission return
  (:5392/:5401; audit :6180/:6206 for the same ordering) — the frozen counter resets even while blocked.
- `scripts/session-value-review.py`: in `decide_gate()`, when no durable progress AND
  `dispatches_in_window == 0` → new action `bootstrap_idle_dispatch`, exit 0 ("starvation
  evidence, not runaway evidence"). ≥1 dispatch with nothing landed still exits 20 — the runaway
  brake is intact. Read errors fail toward blocking.
- Tests: bootstrap verdict; still-20-after-dispatches; reset-persists-while-blocked.

**PR-E `feat/beat-dispatch-rung`** — the beat reaches dispatch (safe to merge anytime; no-ops
until C+D open the wire).
- New `scripts/dispatch-beat.py`: gates ONLY on `autonomy-governor.py dispatch-ok`; wall-clock
  throttle (`logs/.voice/dispatch_beat`, min 1800s); runs the serial engine
  `python3 -m limen dispatch --agent jules --live --limit ${LIMEN_JULES_DISPATCH_LIMIT:-10}`.
  Jules only — remote lane, no local load.
- `sensors.yaml`: `jules-dispatch` (armed_valve_type deliverable), `capacity-fill-refresh`,
  `dispatch-health-refresh` (unfossilize the down-lane receipts). All `source: [metabolize]`.
- `scripts/heartbeat-loop.sh`: ONE rung above the observe short-circuit (:435):
  hourly-throttled `beat-sensors.py --run --source metabolize` — resurrects all 41 dead sensors
  (quota gauge, supply minting, the starvation alarm) even in observe mode; dispatch itself stays
  impossible in observe because dispatch-beat self-gates. Keeps `test_campaign_wake.py:385-391`
  green by construction (no dispatcher strings in the loop file).
- Params: `LIMEN_JULES_DISPATCH*`, `LIMEN_METABOLIZE_SENSORS_*`, `LIMEN_BEAT_*` in parameters.yaml.
- Tests: `cli/tests/test_dispatch_beat.py` + rung-placement text assertion.

**PR-F `fix/release-stale-all-agents`** — drop `--agent jules` from the beat's release-stale
(`heartbeat-loop.sh:467`); `stale_tasks` already handles the no-filter sweep; jules keeps its
confirmed-remote-absence guard. Frees `GH-organvm-hospes-9`. Test: stale codex task released.

**PR-G `feat/work-loan-backfill`** — feed the lane.
- New registry `docs/repo-predicates.yaml` (per-repo executable predicate, owner_surface) seeded
  from `value-repos.json` — the declarative quality bar: no registry entry → refuse to mint.
- `cli/src/limen/work_loan_backfill.py` + `scripts/work-loan-backfill.py`: enrich existing tasks'
  missing WorkLoanV1 fields mechanically (source_origin/horizon/budget_cost derivable; predicate
  only from a PR URL or the registry — NEVER invented; value_case only for value-tier repos).
  Refusals counted with reasons, receipts to `logs/work-loan-backfill.jsonl`. Excludes chronic /
  needs-human / partner-lane; preserves `target_agent` (estate-wide supply, not a jules feeder).
  Batch 25/beat via the tabularius single-writer. Sensor entry armed default **0** until dry-run
  reviewed. Expected honest yield: 250–400 of the 738.
- `docs/jules-supply-templates.yaml`: add value-tier series (today's only registry repo is
  partner-excluded — supply mints nothing even once reachable). Test: every non-excluded registry
  repo passes the value gate; minted packets are loan-ready.
- Tests: `cli/tests/test_work_loan_backfill.py`.

**PR-H `feat/jules-flywheel`** — the ONE predicate proving the compound loop turns.
- `scripts/jules-flywheel.py` + sensor: **exit 0 ⟺** (1) `dispatched_today ≥ 0.8 × target` after
  18 UTC, (2) `landed_3d/dispatched_3d ≥ 0.30` (skipped while `dispatched_3d < 20` — same
  bootstrap escape as the governor), (3) jules open-PR count non-increasing
  (`logs/jules-pr-debt-snapshot.json`). Exit 1 names the failing clause and its owning effector.
- Tests: `cli/tests/test_jules_flywheel.py`.

## Rollout order & interlocks

1. PR-A + PR-B merge first; owner-route-drain runs classification-only 1 day; review verdicts;
   arm `LIMEN_OWNER_ROUTE_DRAIN_APPLY=1` → 308-PR backlog drains in ~2–3 days.
2. PR-C/D/E/F merge → governor self-flips to dispatch with a receipt → beat dispatches at the
   governor's **25/day bootstrap** (the interlock — full 100/day is unreachable until landing
   rate ≥ 0.30, so nothing else needs sequencing discipline).
3. PR-G: dry-run backfill, review refusal counts, arm apply → supply floor ≥100 packets.
4. PR-H: flywheel exit 0 is the program's done-signal.
5. **One human atom** (filed, not nagged): `launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat`
   after PR-E's loop-body edit reaches the live root. No plist edit, no `~/.limen.env` edit,
   no manual policy write.

## Verification

```bash
# per-PR: scoped gates
scripts/verify-scoped.sh
# after rollout, on the live root (read-only):
python3 scripts/autonomy-governor.py explain          # mode=dispatch, restore receipt present
python3 scripts/session-value-review.py --gate --hours 1.5; echo $?   # 0 bootstrap while idle
python3 -m limen dispatch --agent jules --limit 1     # dry-run: admission allowed, track.date=today
python3 scripts/beat-sensors.py --canary              # dispatch-continuity no longer NEVER-RAN
python3 scripts/lane-throughput.py                    # cap/rate table
python3 scripts/jules-flywheel.py                     # THE predicate: exit 0 ⟺ flywheel turns
python3 scripts/check-sensors.py && python3 scripts/check-gates.py && python3 scripts/check-params.py
cd cli && python -m pytest tests/ -q
```

## Guard rails / rollback

- Every new organ: dry-run default, env kill-switch, advisory severity (a failing sensor never
  fails the beat). `AUTONOMY_PAUSED` + explicit policy writes win at every chokepoint.
- Runaway brake preserved: dispatches-without-landings → exit 20; `per_agent.jules: 100` hard cap;
  1800s rung throttle; throughput clamp floors at 25 with a receipt, never silently.
- Rollback = flip the specific env (`LIMEN_AUTONOMY_WINDOW_RESTORE=0`, `LIMEN_JULES_DISPATCH=0`,
  `LIMEN_THROUGHPUT_GOVERNOR=0`, apply-valves to 0); no state is destroyed.
