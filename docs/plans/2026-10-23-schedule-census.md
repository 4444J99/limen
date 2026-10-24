# Schedule census across the GitHub universe

Issue: #3183
PR: #3184

## The real problem

#3178 declares the schedule estate for the planes limen already knows about. The owner's 2026-10-23 ask — *all schedule attempts from the history of my GH universe* — widens the denominator to every repository the owner accounts hold (200+ per `list_repos`, more after the first page), every carrier a schedule can live in, and what became of each attempt. That is a census engine, not a snapshot: an organ that enumerates the universe, reads only the carriers, reconstructs history, and states its denominators before any total.

## What was found (2026-10-23, three reachable repositories)

- This session's GitHub proxy is bound to its configured repositories: `user/repos`, `user/orgs` and `search/code` return 403 and repository-scoped endpoints work only for attached repositories, so the universe-wide run belongs to the host, where `gh` carries the owner's auth and `logs/estate-repos.json` (limen.estate_repos.v1) already holds the denominator.
- The local clones here are shallow (limen history begins 2026-10-12, ops 2026-10-09), so history came through the Commits API, capped and flagged.
- limen: 11 Actions schedules declared, 7 active; `cloudflare-kv-preflight` fires hourly and fails every time; 11 workflows are still registered with Actions but absent from the default branch (temporary diagnostics never retired); 13 workflows switched off by hand; 2,500 scheduled runs in retention.
- ops and ops-witness: every scheduled run since 2026-10-07 refused by GitHub's billing annotation (`L-GITHUB-ACTIONS-BILLING`); ops-witness's `jules-orchestrator` crons were re-added on 2026-09-22 after an earlier removal — the kind of attempt only history shows.
- The six Cloudflare targets, limen's three launchd intervals, 13 claude routines and every dependabot interval are all declared outside Actions and were previously invisible to any schedule gauge.

## Design

`scripts/schedule-census.py` (reader; `_schedules.py` is its parser library): universe from `--repos` / `--repos-file` / the estate cache / `gh repo list` per owner; per repository one tree listing → carriers only (Actions workflows with their live state, wrangler, the ops Cloudflare manifest, vercel, launchd, crontab, systemd timers, dependabot, renovate, cloud-routines) → scheduled-run summary → history (full-clone git log, else the Commits API sampled newest+oldest and flagged truncated). One verdict per repository from evidence only: active · fired-unmeasured · declared-never-fired · firing-but-failing · auto-disabled · manually-disabled · disabled-fork · declared-state-unknown · declared-outside-actions · abandoned-in-history · partial · none · unreachable · error. `--check-registry` lists every repository with an active Actions schedule that no `schedules.yaml` plane declares. Receipt `logs/schedule-census.json` (atomic) + `logs/schedule-census.md`; the organ owns its own 168h interval so the hourly metabolize pass costs one stat. Sensor `schedule-census` (metabolize, advisory), gate `schedule-census-test`, parameters `LIMEN_SCHEDULE_CENSUS*`, reader allowlisted in `check-schedules.py`.

## Human atoms (unchanged)

`L-GITHUB-ACTIONS-BILLING`, `L-SCHED-CLAUDE-REENABLE`, `L-SCHED-READBACKS` — the census measures what they unblock; it cannot pull them.

## Follow-ups

- First universe-wide run on the host: `python3 scripts/schedule-census.py --check-registry --force` (archived repositories included — they hold the historical attempts), then declare each registry gap as a plane or as `declared_off`.
- Retire the 11 limen workflow registrations absent from the default branch (a reap, receipt-backed).
- Fold the census's `registry_gaps` into `schedule-utilization` as a plane-less finding once the first host receipt exists.

## Review round 1 (adversarial, 2026-10-23) — seven must-fixes, all applied

1. An unread scheduled-run listing left `fired` null and the verdict read `declared-never-fired` → `fired-unmeasured`, outside the findings set.
2. A workflow whose contents could not be read was reported "registered with Actions but absent from the default branch" → a path is marked seen when the tree lists it, before any read; the absent-from-tree claim is made only from a complete, untruncated tree; every row carries per-channel read status (`channels`), a `partial` flag and a `scanned_partial` denominator; a partial row never concludes `none`.
3. Crons whose Actions state could not be read fell through to `none` → `declared-state-unknown` / `disabled-fork`; `registry_gaps` lists them with an `unverified` key; the workflows listing is paginated.
4. One malformed carrier (`'list' object has no attribute 'get'`) aborted the whole census → every parser guards its shapes and returns a tri-state (declaration / none / unparseable, the last a note, counted neither way); each `scan_repo` runs under try/except into an `error` row; exit 4 names an engine failure distinctly.
5. A receipt that read nothing counted as fresh for 168h → an incomplete receipt (scanned 0, or more than a quarter unread) earns only `--retry-hours` (24h); a pass that read fewer repositories than the standing receipt is written beside it as `*.last-attempt.json`; exit 2 marks incomplete coverage without findings.
6. `--skip-archived` silently dropped repositories from the denominator → `skipped_archived` list and count in the receipt and ledger; the sensor step no longer passes it (archived repositories hold the attempts this census exists to find); exit 3 whenever scanned is 0 for any reason.
7. `abandoned-in-history` fired on any removed workflow file → requires a cron actually removed; a manual disable needs crons (any workflow can be disabled by hand) while `disabled_inactivity` stands without them (GitHub passes it only on scheduled workflows); a live schedule outside Actions outranks a removal in history.

Folded should-fixes: trailing-comma jsonc; rate guard keyed by API calls (every 50) with a 200-call floor; the budget deadline reaches inside `scan_repo` (remaining channels recorded `skipped:budget`); ledger sections for historical attempts, partial reads, notes, internal errors and skipped archived; `scheduled_runs_in_retention` → `scheduled_runs_listed`; repository metadata 404 → unreachable (missing, renamed, or not visible), never none.

## Review round 2 (Codex on #3184, 2026-10-24) — five P2 findings, all verified by reading, all applied

1. `history_from_git` keyed cron changes by commit alone, so a commit touching two workflows handed both the same cron change → keyed by (commit, path) from the `diff --git` headers; a comment-only edit beside a cron move carries no crons.
2. `history_from_api` ran up to `--history-cap` sequential detail requests with no deadline (≈750 s past the budget at the 25 s timeout, inside the sensor's 1800 s kill) → the deadline reaches inside the sample (and the issues pager); the remainder is recorded `partial` with a budget note, never silently skipped.
3. `exit_code_for` read findings from the one-word repository verdict only, so an auto-disabled or failing schedule beside a healthy active one exited 0 while the totals said otherwise → findings also derive from `gh_workflows_disabled_inactivity` and `workflows_failing_last_scheduled_run`.
4. A failed `gh repo list <owner>` became an empty list and the reduced universe read as complete coverage for 168 h → `resolve_universe` returns the unlisted owners; they land in `denominators.universe_unlisted_owners`, the ledger and the receipt, make the receipt incomplete (retry horizon) and exit 2.
5. `receipt_is_complete` ignored `scanned_partial`, so a transient outage that left every row partially read rested a week → partial rows count toward the unread share.

## Review round 3 and after (Sourcery, Codex, CodeRabbit on 23a60de–b5ccd13) → #3193, stacked PR

Past the two-round bound (`PREC-2026-08-12`) the PR head stops moving for reviewer findings; the verified ones land stacked on `feat/schedule-census`: a listing at `gh repo list --limit` is named `capped:<owner>` and a roster older than `LIMEN_ESTATE_CACHE_TTL_HOURS` yields to a live listing (used caveated as `stale-cache:<fetched_at>` only when that fails); repeated names are scanned once; history requests go through the counting `call`; a failed `git log` is `error`, never an empty history; an unread history makes the row partial (`HISTORY_READ`); runs are keyed by workflow path with the name kept; an empty repository's 409 is `empty`; the ledger is written before the receipt; the sidecar rule compares complete coverage share, and a fresh `*.last-attempt.json` of the same scope counts as the last attempt (no every-beat rescan after a shrunk universe); a fresh receipt answers only a request for the same scope (explicit set, repos file, or the universe).

## Done predicate

`bash scripts/run-pytest-hermetic.sh cli/tests/test_schedule_census.py -q` green; `python3 scripts/check-schedules.py`, `check-sensors.py`, `check-params.py`, `check-gates.py`, `check-runner-coverage.py` exit 0; on the host, `logs/schedule-census.json` exists with `denominators.scanned` equal to the universe, `scanned_partial`, `unscanned_by_budget` and `internal_errors` all 0.
