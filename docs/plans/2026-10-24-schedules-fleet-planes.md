# SCHEDULES registry: own the undeclared fleet by fact — census-derived planes, ceilings, redaction

Issue: #3185
PR: #3186

## The real problem

#3178 declared the planes limen already knew. The 2026-10-23 universe census (#3183 / #3184) then read all 267 repositories the owner accounts hold and found what no plane declared: 206 cron workflows in 73 repositories outside every specific plane (217 fleet-wide; 164 active-or-unknown in the 67 repositories the census lists as registry gaps), 118 live-active, 82 of those the two org templates (49 `stale.yml`, 33 `codeql.yml`) stacked on Monday 06:00 and 09:00 UTC, and 112 of 182 observed workflows failing their last scheduled run (82 in private repositories after 2026-10-08 — consistent with, not proven by, `L-GITHUB-ACTIONS-BILLING`). The census could only re-report that gap every week; the registry had no row, ceiling or verdict for it.

Declaring 67 repositories by name would commit private repository names into the public registry and rot on every archive or rename. The judge panel (three designs, two judges, 22/23 vs 16/21/16) chose the other form: planes that own the remainder by **fact selector** — carrier, scope, visibility, archived flag, live state — with rows derived at read time from the git-ignored census receipt, and **ceilings** pinning the 2026-10-23 counts so growth is red and shrinkage is a number to lower.

## Design

- `scripts/_schedules.py` — `jobs_source: {kind: census, locator, carrier: gh-workflow|launchd, scope: residual|all, visibility?}`; `specific_plane_repos` (the one coverage selector the gate, sensor and census share), `residual_planes`, `derive_census_jobs`, `census_plane_counts` (active / on-the-hour / shared-minute per repository), `census_off_counts`, `declared_off_match`, the receipt loader with states absent / unreadable / wrong-schema / incomplete / stale / present, and `cron_fires_per_day` + `cadence_label` moved here so the census and the sensor never label one cron differently.
- `scripts/check-schedules.py` — A validates census sources, `ceilings`, match-form `declared_off`, the residual visibility partition and a workflows plane's `declared_off` file still existing; with a receipt on the host every ceiling and match rule holds (above = FAIL, below = advisory "lower to N"); B fails a census locator that is not git-ignored; E exempts census planes; **H** fails a committed registry line naming a private repository the receipt lists (disclosed projection tokens exempt; the message names file:line, never the token); **J** fails a rising on-the-hour / shared-minute / declared_off ceiling against the merge-base; the slot map folds census planes to counts.
- `scripts/schedule-utilization.py` — readers `census-receipt` (job-matched: observed = enabled residual workflows whose last scheduled run succeeded within 2× their interval + 1.5d of the receipt; partial rows and ambiguous name joins excluded; overrides `undeclared-off` > `undeclared-growth` > `stagger-regressed`; slack → `readback_overdue`, exit 3; counts-only detail) and `launchctl`; `not_this_host` planes are never red, never stale, not measurable.
- `scripts/schedule-census.py` — shares the selector; records plist `Label`; a gap a residual plane owns carries `owned_by` and is no longer a finding (exit 1 only for a gap `owned_by` null); wrangler crons shadowing ops Cloudflare targets are an advisory section.
- `institutio/governance/schedules.yaml` — planes `github-actions-fleet-private` (ceilings 77 / 67 / 62; declared_off by archive — 10 repositories, 66 workflows — and by live state, 17 + 1), `github-actions-fleet-public` (41 / 40 / 35; 4), `launchd-host` (15 Labels); header: census sources, ceilings, match-form declared_off, evidence kinds, redaction convention R1–R4.
- registries — `LIMEN_SCHEDULE_CENSUS_MAX_AGE_DAYS` (8); sensor escalations; `logs/.gitignore` as a gate path; lever `L-FLEET-TEMPLATE-RETIRE` (the mass template retirement is a human-gated cross-repository write); `L-GITHUB-ACTIONS-BILLING` amended to name the fleet-private plane.

## What the first reading says (receipt 2026-10-23T23:53Z, counts only)

| plane | declared | observed | verdict |
|---|---|---|---|
| github-actions-fleet-private | 75 measurable of 77 active | 6 | underfilled — the private half is dark |
| github-actions-fleet-public | 41 | 39 | full — the public control |
| launchd-host | 15 (distinct plist stems; Labels from the next census) | — | not this host (measured on the Mac) |

## Human atoms

`L-GITHUB-ACTIONS-BILLING` (the refusals), `L-FLEET-TEMPLATE-RETIRE` (the reap), `L-SCHED-CLAUDE-REENABLE`, `L-SCHED-READBACKS` — unchanged in kind; the registry measures what they unblock and cannot pull them.

## Review round 1 (adversarial, 2026-10-24: six lenses, two refuters per finding; 37 of 41 findings survived) — applied

Must-fix, all applied: check H now matches a private name at a sentence end, with a `.git` suffix and in any case; H's exemptions are exactly R1 (`authority.owner_repo` and job ids on authority planes — a `source_of_truth` or an evidence locator never exempts a name); the gate treats an incomplete or stale receipt as unmeasured (B advises, ceilings are compared only for growth, "lower to N" is withheld); `--slot-map --compact` never merges census slots or planes; the launchctl reader honours the receipt state (absent = not this host; unreadable / wrong-schema / incomplete / stale = stale readback).

Should-fix, applied: "lower to N" is advised only from a complete receipt with no partial or unverified rows in the plane (`census_floor_unmeasured`), in both the gate and the sensor; the launchd ceiling is documented as a stem count until a receipt carries Labels; one covered set everywhere (the workflows plane's own repository is read from the registry; the census's `--self-repo` only adds); the public plane owns archived rows; zero rows from a complete receipt is advisory; malformed ceilings fail A without a traceback; a workflow crowded off the receipt's run listing is unmeasurable, not "did not succeed"; the sensor reads the receipt at `jobs_source.locator` and A requires the evidence locator to agree; partial / ambiguous counts cover enabled rows only; J also fails a dropped ratchet key, a dropped per-state ceiling and a deleted rule with a live ceiling, and matches rules by a normalized selector; the template count is 82 of 118 (49 `stale.yml`, 33 `codeql.yml`), the residual is 206 workflows in 73 repositories, codeql fires mostly Monday 06:00; `L-GITHUB-ACTIONS-BILLING`'s predicate tests its fleet-private clause and `L-FLEET-TEMPLATE-RETIRE`'s requires a complete receipt newer than the lever; tests pin each of these (the "active may rise" step now changes a value; the plain-directory step sets `GIT_CEILING_DIRECTORIES`; a tracked-but-ignored receipt fails B; scope `all`, a lone residual plane, a str state and a base without the plane are covered).

Nits, applied: `cadence_label` treats a day field that covers every day as unrestricted and requires every month for the named labels; the header states the unverified rule; the baseline redaction step uses separate lines.

Not covered by the review: live launchctl on a Mac, the private plists' Label/stem agreement, a live census rerun.

## Done predicate

`bash scripts/run-pytest-hermetic.sh cli/tests/test_schedules_registry.py cli/tests/test_schedule_census.py -q` green; `python3 scripts/check-schedules.py`, `check-sensors.py`, `check-params.py`, `check-gates.py`, `check-his-hand.py` exit 0; with the receipt on the host, `check-schedules.py` reports every ceiling met and `schedule-utilization.py --json` scores the two fleet planes with no repository name in any detail string; without it, the three planes read `not_this_host`.
