# Continuous PR lifecycle auto-typing rung

Issue: #1978
PR: #1988

## Context

Close the arrival-rate decay loop: the estate drain was one-shot, so pr-debt --check rebounds red as new mechanical PRs arrive; ship the beat-wired auto-typing rung (dry-run until levered)

The `/verify` finding, measured: the drain typed 283 lifecycle-untyped PRs to zero and
`scripts/gitvs.py pr-debt --check` rebounded 0→2 within the hour, purely from new inflow. Nothing
in the beat typed arrivals, and the task's own predicate reads the live census — so "done" un-did
itself hourly and the morning stale-pr-sweep kept re-reporting a small nonzero untyped count.

## Resolved design decisions

1. **A trickle rung, not a second run of the drain organ.** The estate-manifest drain's
   `_preflight_repo` aborts an entire apply batch on one drifted head, and dependabot rebases
   constantly — so the drain is structurally the wrong shape for a continuous arrival stream.
   Binds: `scripts/pr-lifecycle-autotype.py`, sensor `github-pr-autotype` in
   `institutio/governance/sensors.yaml`. Every candidate is re-checked at effect time and declines
   individually; a batch abort is never reachable.

2. **Scope is derived from the estate authority, never a second literal.** The rung enumerates the
   same owner set `pr-debt --check` measures, via `scripts/gitvs.py`'s `owners(load_estate())` over
   `institutio/github/estate.yaml`. Measured at the time of writing: 220 of 361 open dependabot PRs
   (61%) live in shelf orgs outside the two-owner literal the sibling drains carry, with
   `organvm-iii-ergon` alone holding 128. A narrower scope would have delivered 39% of the contract
   while printing a confident `cohort=0` forever. This also removes a use of the
   baselined-undeclared `LIMEN_OWNERS` in favour of the declared `LIMEN_GITVS_OWNERS`.

3. **The disposition stays fail-closed `lifecycle:blocked`; the delivery upgrade stays a separate
   human gate.** Typing an arrival is a classification, not a decision to merge it. Binds: lever
   `L-DEPENDABOT-DELIVERY-ARM` (issue #1947) remains the operator's, untouched by this change.

4. **The organ ships LIVE in dry-run; only the mutation is gated.** Receipts accrue from the first
   beat so the arming decision is made on collected evidence rather than on a promise. Binds: lever
   `L-PR-AUTOTYPE-ARM` (issue #1978) and parameter `LIMEN_PR_AUTOTYPE_APPLY` in
   `institutio/governance/parameters.yaml`, whose note carries the `fleet_runtime: "1"` arming
   contract (the #576 dark-switch lesson).

5. **The discharge predicate is deliberately NOT changed to read the recorded ledger.** The
   alternative fix — having `pr-debt --check` read the recorded scoreboard rather than the live
   census — would make the predicate green by narrowing what it looks at. Arrival drift and
   human/classification rows *should* surface. Binds: `scripts/gitvs.py` `pr_debt` remains
   unmodified by this change; the rung answers the decay instead of hiding it.

6. **Absence is never rendered as health.** Every read can fail and a failed read produces the same
   empty list a drained estate does, so the searches return `(rows, ok)`: a failed visit is
   receipted as `read-failed`, reported as `cohort=UNKNOWN`, and exits non-zero, which is what makes
   the sensor's `escalation:` string reachable at all. Binds: `scripts/pr-lifecycle-autotype.py` and
   `cli/tests/test_pr_lifecycle_autotype.py`; precedent class
   `PREC-2026-07-04-friction-shallow-first` is not the one at issue here — the governing measured
   defect is this file's own `--` separator regression, where a malformed argv fail-open printed a
   confident empty cohort over an unread estate.

7. **Budgets are bounded and announced.** `archived:false` excludes read-only repos at the source
   (the census already types them from a non-label source, so they can never leave a label-absence
   search), with an effect-time `_repo_archived` rail so the guarantee does not rest on a single
   read; `--limit` bounds effects rather than iterations, matching what
   `institutio/governance/parameters.yaml` already declared it to be. Truncation prints `residual=N`.

## Steps

1. Author the organ `scripts/pr-lifecycle-autotype.py` in the owner-route-drain posture (dry-run
   default, `--apply` / `LIMEN_PR_AUTOTYPE_APPLY=1`, `logs/AUTONOMY_PAUSED` forces observation-only,
   per-run `--limit`, one JSONL receipt row per verdict).
2. Declare the beat sensor `github-pr-autotype` as ONE `institutio/governance/sensors.yaml` entry —
   zero shell edits, per IF-SENSOR-REGISTRY — plus its parameter declarations.
3. File the arming lever `L-PR-AUTOTYPE-ARM` in `his-hand-levers.json` in the same change, so the
   deliverable valve reads PARKED rather than SILENT-OFF to `scripts/armed-valve-audit.py`.
4. Cover it with hermetic tests (fake `gh`, no network) in `cli/tests/test_pr_lifecycle_autotype.py`.
5. Prove it live in dry-run against the real estate before pushing, and adversarially review the
   organ pre-merge before it can mutate anything.
6. Ship on the normal rail: `scripts/verify-scoped.sh` → PR → `scripts/merge-policy.sh` →
   `scripts/await-pr.sh --merge`.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** That the organ reports health it never
  measured. Two instances were found and fixed before merge, both of the same class: a malformed
  `gh` query whose fail-open rendered an unread estate as `cohort=0`, and an owner scope narrower
  than the predicate's that would have left 61% of the arrival stream unread. Both printed
  confident, green, wrong output. The residual risk is a third instance somewhere not yet looked
  at — which is why the read-failure path is now receipted and non-zero rather than silent.
- **Second risk: the rung mutates something it should not.** Mitigated by an effect-time author
  rail (only configured mechanical authors are ever typed, whatever the search returned), the
  pause marker, an effects-bounded `--limit`, and shipping disarmed so a day of receipts precedes
  any write.
- **Third risk: it becomes invisible.** The sensor is `severity: advisory`, so a permanently broken
  rung cannot fail the beat. Partly mitigated — a non-zero now prints the escalation line — and
  named here rather than claimed solved. `owed:` a liveness signal for advisory rungs generally.

## Verification

- `bash scripts/verify-scoped.sh` → `Scoped verification passed` (15 cheap gates; `check-sensors`
  OK at 85 sensors with panel-default parity; `check-params` OK, no new hardcodes; `pytest-cli` and
  `pytest-api` PASS).
- `bash scripts/run-pytest-hermetic.sh cli/tests/test_pr_lifecycle_autotype.py -q` → 20 passed in
  0.16s (the runtime is the hermeticity proof — no subprocess spawns).
- `python3 scripts/pr-lifecycle-autotype.py --limit 5` against the live estate →
  `DRY-RUN owners=10 cohort=2 examined=2 typed=2 skipped=0 human_unlabeled=125`.
- `python3 scripts/beat-sensors.py --list | grep github-pr-autotype` → scheduled, cadence 4,
  advisory, without `--apply` (the valve ships disarmed).
