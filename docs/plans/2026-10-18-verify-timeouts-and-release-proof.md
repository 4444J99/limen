# Pick-up plan: close the agent-doable residue of the TMB acceptance-gap session

Issue: #2898
PR: (pending)

(Lane 2 is owned by #2928 and ships as its own PR; this plan's header names the lane-1 chain because
`check-session-phase.py` accepts exactly one `Issue: #N` line.)

## Context

The prior session merged every engineering lane (Limen #2938 etc., TMB #5–#15) but ended without a
passing closeout predicate and with two tooling defects that cost it most of its time. Verified live
this session (2026-10-18):

- **#2898 is real and open.** `scripts/verify.py:838-839` computes
  `min(cli_timeout, row_timeout)`, so a registry `timeout_seconds` can only *shorten* a gate. `pytest-cli`
  declares 1500 s (`institutio/governance/gates.yaml:1210`) but is killed at the 300 s CLI default;
  `--total-timeout-seconds` defaults to 600 (`verify.py:1180`). This is the "600 s window too short"
  that burned ~7 verification attempts on #2938.
- **#2928 is real and open.** `retire_released_worktree` (`cli/src/limen/worktree_abandonment.py:326`)
  rejects any `remote_ref` not under `refs/heads/`. After a squash merge deletes the branch, only
  `refs/pull/N/head` survives, so `release` returns `retained / invalid-release-proof`. ~13 clean merged
  worktrees under `~/Workspace/.limen-worktrees/` are stuck waiting on the 6 h reclaim window.
- **The closeout "blockers" are environment seams, not missing code.** `rfc8785` is absent from the
  Homebrew Pythons but present in `cli/.venv` (py3.11, with click/yaml/pytest). The broker error
  (`BrokerUnavailable`) is only because this shell hasn't exported `LIMEN_CONDUCT_URL/TOKEN`; both are
  already present in `~/.limen.env` (count 2, values never printed).
- Writer lease: `allowed: true` (5 codex leases held by other sessions — not mine, not touched).
- Live checkout is behind `origin/main` by 4 and carries an **uncommitted `AGENTS.md` rewrite (317+/364−)
  that is not from this thread** — leave it alone.

## Out of scope (human-gated, already homed — state once, do not re-surface)

Safari accessibility prompt (TMB #14) · second custody disk (L-TMB-INGRESS-SOURCE-MOUNT) · soak decision
(TMB #16) · BlackHole install · history purge (declined; L-TMB-HISTORY-REMOVAL) · closing #2933 (fix landed;
only the human closes).

## Lane 1 — fix #2898: registry timeouts must be able to extend a gate

Worktree/branch: this worktree (`worktree-fix-verify-registry-timeouts-20261018`), off `origin/main`.

Change `scripts/verify.py`:
- `--gate-timeout-seconds` default `None` (env `LIMEN_VERIFY_GATE_TIMEOUT_SECONDS` still counts as
  explicit). Per-gate budget = registry `timeout_seconds` if declared, else 300 (the old default).
  When the operator *does* pass a value, it is a **ceiling** (`min`), preserving override semantics.
  Edit the single site at `run_gate_wave` (`verify.py:838-839`) and thread the "explicit?" bit through
  `cmd_changed` (`:956`).
- `--total-timeout-seconds` default `None` → `max(600, longest implicated registry budget + 300)`,
  still hard-capped at the existing 1800 s (`:963`). Compute after the implicated set is resolved; the
  keeper-owned `LIMEN_WORK_KEY` admission block (`:964-984`) keeps `min`-ing over it unchanged.
- Serialized-lock wait (`:1106`) keeps using the effective per-gate budget.
- Verified non-blockers: `bounded_seconds` (`verify.py:436`) admits 1500 (cap 1800);
  `verify-scoped.sh` passes no timeout flags; `pr-gate.yml:56,88,129,139` already pass explicit
  1500/1700, which become ceilings under this change → CI behaviour is identical.
- Second owner, noted on #2898 rather than claimed closed: a session with `LIMEN_WORK_KEY` set gets its
  verification window from the keeper (`reserve_growth`, `verify.py:964-984`) and is `min`-ed over the
  new default. This session has no work key, so the fix is observable here; keeper-bound dispatch lanes
  need the keeper's `verification` growth duration checked separately.

Tests (extend `cli/tests/test_verify_host_admission.py`, which already exercises these flags; also check
`scripts/tests/verify-parallel.test.sh` for asserted 300/600 literals):
- fixture gate declaring `timeout_seconds` > CLI default is **not** killed at the default;
- explicit operator ceiling still shortens it;
- default total deadline ≥ largest implicated serialized gate, ≤ 1800.

## Lane 2 — fix #2928: accept `refs/pull/N/head` as release proof

Worktree/branch: a second worktree `fix/release-proof-pull-ref-20261018`, off `origin/main`
(separate concern → separate PR).

Change `retire_released_worktree` (`worktree_abandonment.py:326`): accept
`^refs/pull/\d+/head$` in addition to `refs/heads/*`. The existing exact-tip check
(`ls-remote` must equal `expected_head`, rechecked after the network call) stays unchanged — a
`refs/pull/N/head` equal to the head proves the commit is durably on origin exactly as a branch tip
would, and only the disposable checkout is removed (all refs retained). Decision: **no new `gh` call**
inside this function (issue #2928 floated checking MERGED); it would add a network/auth dependency to a
function whose whole proof is "origin holds the exact head".

Tests (extend `test_release_retirement_preserves_uncertain_work_and_is_idempotent`,
`cli/tests/test_recovery_execution_limits.py:82`): add `squash-merged` (delete remote branch, push
`refs/pull/1/head` at the head → `completed`, idempotent re-run `already-absent`) and
`pull-ref-wrong-tip` (→ `retained`). Update the `release` CLI help in `scripts/worktree-abandonment.py`.

## Lane 3 — reap this thread's spent worktrees (after lane 2 is merged and installed)

For each of: `ab-parent-2938`, `av-encrypted-custody`, `av-second-device-custody`, `cli-lock-zstandard`,
`closeout-runtime-test`, `merge-policy-diag`, `sealed-custody`, `session-closeout-01Tq`,
`tmb-ingress-results`, `tmb-levers`, `tmb-plan`, `tmb-session-closeout` (all under
`~/Workspace/.limen-worktrees/`): confirm its PR is MERGED via `gh pr view` (squash repo — ancestry is a
false negative), then `scripts/worktree-abandonment.py release` **dry-run first**, then `--apply` with
`--remote-ref refs/pull/N/head`. Do **not** touch any other worktree in `git worktree list` (codex
sessions, `agent-docs-correct`, `dynamic-routing-residue`, `hook-bounds-*`, etc. belong to other lanes).
Repeat for the `time-moment-brief` repo's merged worktrees. Fast-forward the live checkout with
`scripts/sync-release.sh` only if it can be done without disturbing the foreign `AGENTS.md` edit;
otherwise report it.

## Lane 4 — run the closeout predicate for real

One scratch script in `$CLAUDE_JOB_DIR/tmp` (judged rail forbids chains): `set -a; source ~/.limen.env`,
then `PATH="<repo>/cli/.venv/bin:$PATH"`, then
`scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json`, run **bare twice**
(idempotence = two bare exit-0 runs). `LIMEN_GATE_PYTHON` does **not** steer this script: with explicit
args it `exec`s the installed layout's `venv/bin/python` (PR #2910, merged) or else a bare `python3`
(`no-tasks-on-me.sh:25-31`), so from a plain checkout the PATH prefix is the lever. No code change
needed. If the broker still refuses with the env sourced, that is a genuine blocker → `BLOCKED: <atom>`
once, filed with its registry owner, not recited.

## Verification

- Per lane: `bash scripts/run-pytest-hermetic.sh <the one test file> -q` (never the full suite — the
  scope guard denies it, and main's full suite is already known red under load), then ruff
  (`python3 -m ruff check` + `format --diff` on touched files), then
  `bash scripts/verify-scoped.sh` on the exact tree. Until lane 1 merges, use the documented workaround
  `--total-timeout-seconds 1800 --gate-timeout-seconds 1500`.
- Lane 1 acceptance proof: `scripts/verify-scoped.sh` **without** workaround flags runs `pytest-cli`
  past 300 s on a cli-touching diff (A/B against the parent commit's `<sha>^`, not a branch name).
- **Merge rule for the load-red `pytest-cli` gate (both lanes implicate it via `cli/**`):** the gate runs
  the full ~1200-test suite regardless of my single-file runs, and main's full suite is already red on
  this host (17 load-dependent failures at the parent of #2938). Capture each lane's failing set, A/B it
  against the parent's set (extract baseline from `0f761c08a^`-style parent SHAs — the
  `ab-parent-2938` worktree is still at `0f761c08a` — never a branch name, and assert a marker is absent
  from the baseline). Merge only if the lane's set ⊆ the parent's set, and state the A/B in the PR body.
  This is the #2938 precedent the human already ratified; a *new* failure outside the parent set stops
  the merge and is fixed first.
- Read each predicate's own exit code (no pipes). Merge per `scripts/merge-policy.sh <PR#>` /
  the registry fast lane; neither lane touches a website deploy-trigger path.
- Status words reported separately: merged (on origin/main) / live (installed runtime contains it) /
  observed (reap receipts, closeout exit codes).

## Durable homing

Issues #2898 and #2928 are the owners; each lane's PR closes the loop on its issue. This plan is
committed on lane 1's branch as `docs/plans/2026-10-18-verify-timeouts-and-release-proof.md` (renamed
from this scratch name; the dated filename is what `check-session-phase.py` scans) and
`scripts/check-session-phase.py` is run bare to confirm exit 0 before pushing. Lane 3's "installed"
check: if the live checkout cannot fast-forward past the foreign `AGENTS.md` edit, run
`worktree-abandonment.py` with `PYTHONPATH=<lane-2-worktree>/cli/src` instead.
