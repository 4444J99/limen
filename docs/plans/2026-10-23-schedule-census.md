# Schedule census across the GitHub universe

Issue: #3183
PR: (pending)

## The real problem

#3178 declares the schedule estate for the planes limen already knows about. The owner's 2026-10-23 ask — *all schedule attempts from the history of my GH universe* — widens the denominator to every repository the owner accounts hold (200+ per `list_repos`, more after the first page), every carrier a schedule can live in, and what became of each attempt. That is a census engine, not a snapshot: an organ that enumerates the universe, reads only the carriers, reconstructs history, and states its denominators before any total.

## What was found (2026-10-23, three reachable repositories)

- This session's GitHub proxy is bound to its configured repositories: `user/repos`, `user/orgs` and `search/code` return 403 and repository-scoped endpoints work only for attached repositories, so the universe-wide run belongs to the host, where `gh` carries the owner's auth and `logs/estate-repos.json` (limen.estate_repos.v1) already holds the denominator.
- The local clones here are shallow (limen history begins 2026-10-12, ops 2026-10-09), so history came through the Commits API, capped and flagged.
- limen: 11 Actions schedules declared, 7 active; `cloudflare-kv-preflight` fires hourly and fails every time; 11 workflows are still registered with Actions but absent from the default branch (temporary diagnostics never retired); 13 workflows switched off by hand; 2,500 scheduled runs in retention.
- ops and ops-witness: every scheduled run since 2026-10-07 refused by GitHub's billing annotation (`L-GITHUB-ACTIONS-BILLING`); ops-witness's `jules-orchestrator` crons were re-added on 2026-09-22 after an earlier removal — the kind of attempt only history shows.
- The six Cloudflare targets, limen's three launchd intervals, 13 claude routines and every dependabot interval are all declared outside Actions and were previously invisible to any schedule gauge.

## Design

`scripts/schedule-census.py` (reader; `_schedules.py` is its parser library): universe from `--repos` / `--repos-file` / the estate cache / `gh repo list` per owner; per repository one tree listing → carriers only (Actions workflows with their live state, wrangler, the ops Cloudflare manifest, vercel, launchd, crontab, systemd timers, dependabot, renovate, cloud-routines) → scheduled-run summary → history (full-clone git log, else the Commits API sampled newest+oldest and flagged truncated). One verdict per repository from evidence only: active · declared-never-fired · firing-but-failing · auto-disabled · manually-disabled · abandoned-in-history · declared-outside-actions · none · unreachable. `--check-registry` lists every repository with an active Actions schedule that no `schedules.yaml` plane declares. Receipt `logs/schedule-census.json` (atomic) + `logs/schedule-census.md`; the organ owns its own 168h interval so the hourly metabolize pass costs one stat. Sensor `schedule-census` (metabolize, advisory), gate `schedule-census-test`, parameters `LIMEN_SCHEDULE_CENSUS*`, reader allowlisted in `check-schedules.py`.

## Human atoms (unchanged)

`L-GITHUB-ACTIONS-BILLING`, `L-SCHED-CLAUDE-REENABLE`, `L-SCHED-READBACKS` — the census measures what they unblock; it cannot pull them.

## Follow-ups

- First universe-wide run on the host: `python3 scripts/schedule-census.py --check-registry --skip-archived --force`, then declare each registry gap as a plane or as `declared_off`.
- Retire the 11 limen workflow registrations absent from the default branch (a reap, receipt-backed).
- Fold the census's `registry_gaps` into `schedule-utilization` as a plane-less finding once the first host receipt exists.

## Done predicate

`bash scripts/run-pytest-hermetic.sh cli/tests/test_schedule_census.py -q` green; `python3 scripts/check-schedules.py`, `check-sensors.py`, `check-params.py`, `check-gates.py`, `check-runner-coverage.py` exit 0; on the host, `logs/schedule-census.json` exists with `denominators.scanned` equal to the non-archived universe and `unscanned_by_budget` empty.
