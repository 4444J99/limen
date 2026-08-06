# Wire the PR-debt recorder — the probe exists, the producer never ran

Issue: #1853
PR: #1854

## Context

`scripts/check-ideal-forms.py --measure` exits **1** with verdict **DRIFT**. Measured 2026-08-05:
20 ideals — 6 at-ideal, 7 carrying distance, 7 unmeasured. Two of those readings are defects in the
*measurement apparatus itself*, not in the things measured, and this plan closes both.

**Defect 1 — IF-AMALGAMATION: the probe has no producer.** `scripts/pr-debt-trend.py --check`
exits 1 with `STALE — the newest observation is 11d old (tolerance 3d)`. Its own header names the
cause exactly: the producer is `python3 scripts/gitvs.py pr-debt --check --json`, and it is *wired
to nothing* — no sensor, no gate, no beat rung. Owner of record `GITVS-UNCAPPED-PR-DEBT-0715`.

The git log makes the failure sharper than the prose did. Every observation in the "series" is a
hand-authored feature PR:

```
0f44105e 2026-07-25  docs(gitvs): record exact-owner lifecycle fixed point (#1541)   1164
46296655 2026-07-24  docs: preserve laptop-wide recovery continuation (#1495)        1117
ad0565a4 2026-07-24  feat: close PR lifecycle estate at fixed point (#1508)          1115
ff5de9dc 2026-07-23  Type PR lifecycle debt explicitly (#1503)                       1111
5c1727f0 2026-07-22  feat: add uncapped exact PR debt census (#1337)                 1059
```

There was never a recorder. The series was a **side effect of five unrelated PRs that happened to
regenerate the ledger**, and it stopped the moment that work stopped. The measured trend over its
whole life is **+105 in three days** against an ideal whose word is "monotonically *down*" — and
then eleven days of silence that the naive reading scores as improvement.

**Defect 2 — IF-MAIL: the prose lags the healed system.** `check-mail-answered.py` reports
`OK — reply_owed=5 drafted=5 undrafted=0` (exit 0), while the ledger still says `PARTIAL`. Check D
of `check-ideal-forms.py` flags this as drift, correctly: *a Status line contradicting its own probe
is drift, not a stale note*. This is the good direction for drift to point — the system healed and
the story didn't notice — and it is a one-line correction.

Both are the same species, the one this whole workstream keeps finding: **a value produced and
consumed by nothing.**

## Resolved design decisions

- **D1 — the recorder is a `--record` verb on `pr-debt-trend.py`, not a new script.** Charter
  § Parallel Exploration: route through an existing canonical surface, never fork parallel
  substrate. That file already owns the concept, already knows the ledger path, already names the
  producer, and its header already declares this the row's next form: *"a real probe needs a
  committed series, so the debt-trend recorder is this row's next form."* The consumer becomes the
  recorder; nothing new is invented.

- **D2 — the recorder self-throttles on wall-clock, not on beat count.** The beat is adaptive
  (`LIMEN_LOOP_MIN=120` … `LIMEN_LOOP_MAX=1800`), so a `cadence: N` means anywhere from 16 minutes
  to 4 hours of wall-clock. A full paginated open-PR census across the estate must not run on the
  busy end of that range. `--record` therefore checks the newest observation's age first and exits
  0 as a no-op unless it exceeds `LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS` (default 20 — comfortably
  inside the probe's own 3-day tolerance, with two missed runs of margin). The cheap age check runs
  every cadence; the expensive census runs only when due.

- **D3 — an observation lands as a PR via `ship-docs.sh`, because that is what the charter already
  requires of every docs-class write.** `docs/github-pr-debt-ledger.json` is docs-class and not a
  deploy trigger (verified against `gates.yaml:deploy_triggers`). The alternatives both fail:
  `capture.sh` explicitly snapshots a live default-branch checkout to a *side ref* and "never
  commits or pushes directly," so the observation would never enter `main`'s history where the
  probe reads it; and `sync-release.sh`'s dirt capture only fires when the checkout is parked off
  the release branch, which is the exact state the fleet works to prevent. Shipping a PR also
  preserves the historical shape — observations always arrived as PRs — while replacing the
  accident with a cadence.

- **D4 — no PR churn: ship only on change.** If the census content is byte-identical to the
  committed ledger, `--record` writes nothing and opens nothing. A PR-debt recorder that adds a PR
  per beat would be self-refuting.

- **D5 — the sensor entry is `github-pr-debt`, a sibling of `github-estate-reconcile`.** Same owner
  (`gitvs`), same `[heartbeat]` source, `severity: advisory` so an incomplete census surfaces with
  `↑` and never breaks the fail-open beat. Adding a beat sensor is **one registry entry** — the
  hand-wired shell block is not an option (`sensors.yaml` header; `check-sensors.py` enforces).

- **D6 — IF-MAIL's ledger status is corrected to match its probe, not the probe relaxed to match
  the prose.** The registry's rule is that the number is derived and the prose follows. Correcting
  the prose is the whole repair.

- **D7 — the cross-repo frontier is a separate concern and is NOT in this branch.** Six rows carry
  `probe: null` with honest reasons that cluster into four kinds (outside the tree / in the owner
  repo / a live condition / an event not a state). Giving those rows probes means a new probe
  `environment` and event capture — a different concern, on a different branch, per the charter's
  one-concern rule. Filed as its own issue.

## Steps

1. `scripts/pr-debt-trend.py` gains `--record`: age gate → `gitvs.py pr-debt --write-ledger` →
   change detect → `ship-docs.sh` → report. Plus `LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS`.
2. `institutio/governance/sensors.yaml`: new `github-pr-debt` sensor running `--record`.
3. `institutio/governance/parameters.yaml`: declare the new gate/cadence/interval envs.
4. `docs/IDEAL-FORMS-LEDGER.md`: correct IF-MAIL's status; update IF-AMALGAMATION's evidence to
   name the recorder rather than the vacuum.
5. File the cross-repo-probe frontier (D7) as its own issue.

## Premortem

- **The recorder ships a PR while the estate already has 1,164 open.** Bounded by D4 (change-only)
  and D2 (≤ ~1/day). Net effect is one docs PR per day that self-merges via `merge-policy.sh` —
  and the thing it measures is precisely the debt it must not add to.
- **`gitvs.py pr-debt` is expensive/rate-limited.** D2's age gate is the throttle; `severity:
  advisory` means a timeout surfaces as `↑` and never breaks the beat.
- **`ship-docs.sh` refuses the path.** Verified: `docs/**` is not in its website-sensitive refusal
  list and not a deploy trigger.
- **The recorder runs on a shallow CI checkout and misreads history.** `--record` inherits the
  file's existing `environment: host` discipline; the sensor is `[heartbeat]`-sourced only.

## Verification

- `python3 scripts/pr-debt-trend.py --record --dry-run` → reports the decision without shipping.
- `python3 scripts/check-sensors.py` → registry ↔ script ↔ parameter-panel parity holds.
- `python3 scripts/check-params.py` → new envs declared.
- `python3 scripts/check-ideal-forms.py --measure` → **no DRIFT line** (the IF-MAIL repair).
- `python3 scripts/beat-sensors.py --list` → the new sensor appears in the derived matrix.
- `bash scripts/verify-scoped.sh` → green on the diff.
