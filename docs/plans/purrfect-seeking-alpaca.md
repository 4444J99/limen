# Fewer permission prompts — read-only allowlist additions

## Context

`/fewer-permission-prompts` asks for a prioritized set of read-only patterns, scanned from recent
transcripts, merged into the project `.claude/settings.json` under `permissions.allow`.

Scan: 50 most-recently-modified transcripts under
`.agent-runtime/claude/projects/*/*.jsonl` (all Limen worktree projects plus `-Users-4jp`).
Bash commands were split on `&& || ; | newline` and ranked by leading command + subcommand.

Most of the top of the ranking needs no rule: `git -C <path> …` reads, `gh pr/issue/run/repo view|list|checks`,
`grep`, `sed -n`, `find`, `date`, `ls`, `cat` are auto-allowed, and `git add/commit/push/fetch/switch`, `gh pr create/merge/edit`,
`gh issue create/comment`, `shasum`, `sqlite3`, `bash scripts/verify-scoped.sh *`, `bash scripts/merge-policy.sh *`,
`bash scripts/run-pytest-hermetic.sh *`, `python3 -m ruff|pytest *` are already in the allowlist.

What remains are **repo status/check scripts**, invoked as `python3 scripts/<x>.py` (relative) or
`python3 /Users/4jp/Workspace/limen/scripts/<x>.py` (live-checkout absolute). Each was checked against its source
(`grep` for `write_text|open(..,"w"|"a")|mkdir|add_argument`) so a pattern is only granted for a form that cannot write.

## Patterns to add (ranked by observed count)

| # | Pattern(s) | ≈Count | Why it is safe |
|---|---|---|---|
| 1 | `Bash(python3 /Users/4jp/Workspace/limen/scripts/host-work-admission.py status)` + `… status *` | 97 | `status` is a read-only lease/capacity report (relative form already allowed; the absolute form is what prompts) |
| 2 | `Bash(python3 scripts/check-runtime-lag.py)`, `… *`, and absolute twin | 24 | 0 write sites; only flag is `--json` |
| 3 | `Bash(python3 scripts/reap-branches.py --check)` + absolute twin | 21 | `--check` documented "(read-only)"; exact form only — `--apply`/`--force` stay prompted |
| 4 | `Bash(python3 scripts/credential-wall.py --check)` + absolute twin | 14 | exact `--check`; `--sync` (writes issue #320) stays prompted |
| 5 | `Bash(python3 scripts/check-session-phase.py)` + absolute twin | 13 | exact form; `--write-baseline` stays prompted |
| 6 | `Bash(python3 scripts/check-plan-decisions.py)`, `… *`, and absolute twin | 13 | 0 write sites; flags `--check`/`--all` only |
| 7 | `Bash(python3 scripts/check-live-checkout.py --no-receipt)` + absolute twin | 11 | `--no-receipt` is "report only"; the bare form writes `logs/live-checkout-currency.json`, so it is **not** granted |
| 8 | `Bash(python3 scripts/check-agent-docs.py)` | 7 | 0 write sites, no flags |
| 9 | `Bash(python3 scripts/check-his-hand.py --check)` | 6 | 0 write sites; exact form |
| 10 | `Bash(python3 scripts/check-gates.py)` | 3 | 0 write sites |
| 11 | `Bash(python3 /Users/4jp/Workspace/limen/scripts/host-work-admission.py --help)`, `… capabilities` | 10 | help/capability listing (relative forms already allowed) |
| 12 | `Bash(bash scripts/verify-scoped.sh)`, `Bash(scripts/verify-scoped.sh)` | many | bare no-arg forms of rules the user already granted (`… *`); consistency only |

About 28 literal entries after de-duplication against the existing list. Existing entries are untouched.

## Deliberately skipped (and why)

- **Auto-allowed, no rule needed:** `git -C … status|log|diff|grep|merge-base|ls-tree|ls-remote|rev-parse`, `gh pr view|list|checks`, `gh issue view|list`, `gh repo view|run view|list`, `grep`, `sed -n`, `find`, `date`, `ls`, `cat`.
- **Arbitrary code execution:** `python3 -I -c`, `python3 -c`, `uvx`, `uv run`, `env … python3`, `python3 -I <scratch>.py`, `mcp__claude-in-chrome__javascript_tool` (61), `mcp__claude-in-chrome__computer` (24).
- **Mutating:** `scripts/merge-drain.py` (submits merges), `scripts/memory-ticket.py`, `host-work-admission.py acquire|release|refresh`, `perl -pi -e`, `ship-docs.sh`, `reap-branches.py --apply|--force`, `credential-wall.py --sync`.
- **Writes a receipt/log by default:** bare `check-live-checkout.py`, `worktree-debt.py`, `check-knowledge-alive.py`, `check-prerewrite-containment.py --write-ledger`.
- **Executes config-named code:** `python3 -m mypy` (plugins load from config). `ruff` is already allowed; mypy is left prompting.
- Anything below ~3 uses.

## Implementation (after approval)

1. Work in this worktree (`worktree-chore-fewer-permission-prompts-20261018b`) — a mutation lane must not touch the live checkout.
2. Edit `.claude/settings.json`: append the new strings to `permissions.allow` only; preserve every existing entry and key order; no `deny`/`ask` changes.
3. Validate JSON: `python3 -I -c "import json; json.load(open('.claude/settings.json'))"`.
4. `bash scripts/verify-scoped.sh` (bare) on the final tree; commit; push; open PR; merge via `scripts/merge-policy.sh <PR#>` exit 0 → `gh pr merge … --match-head-commit`.
   If the harness's self-modification boundary blocks the settings edit, stage the validated file and hand over the single copy-paste (charter: Standing Autonomy & Compliant Gate Reroute).

## Verification

- `git diff` shows only added lines inside `permissions.allow`; the existing 74 entries are intact.
- JSON parses; no duplicate strings; no wildcard on an interpreter, shell, package runner, or task runner.
- Spot-check next session: the absolute-path `host-work-admission.py status` and the `check-*` scripts run without prompting.

---

# Addendum 2026-10-19 — make the session closeout predicate pass

## Context

The operator ran the closeout predicate for this session (`scripts/no-tasks-on-me.sh --session-id
20ca0534-… --worktree … --receipt …/session-closeout.json --json`). Their first attempt failed only because
my hand-off text carried a `<this worktree>` placeholder that the shell parsed as a redirect. With real paths
the predicate now **measures** (exit 1, `registration_witness: observed`): the broker quota (#2054) reset with
the new day, so the earlier "unmeasured" block has lifted. It reports three classes of finding, each traced to
the checker's code in `cli/src/limen/session_closeout.py` and `cli/src/limen/process_ownership.py`:

| Finding | Mechanism | Cause | Fix |
|---|---|---|---|
| `owned implementation changed since verification` ×3 | `session_closeout.py:372`: `git diff --name-only <verification head> HEAD -- <owned paths>` must be empty | I added the audit README edit and the two `tooling/` scripts in the same commit as the receipt, after the head I verified (`dbdc5b06`) | New receipt commit on top of a base that already contains them; verify at that base |
| `unattributed committed path` ×~75 | `session_closeout.py:400`: every path in `base_head..HEAD` must be an evidence path, owned, or retained | I set `base_head` to the session start (`087ecd58f`), so every other session's merged paths since then count as mine; two `context-*.txt` evidence files were also unreferenced | Precedent (`session-closeout-lesson-harvest-20261018`) sets `base_head` to the receipt branch's fork point = the verification head. Reference or drop the `context-*` files |
| `session worktree has surviving or unattributed processes` | `process_ownership.py:310-329`: in-scope, non-`excluded` processes fall to `unknown / ownership_unresolved` | The only offender is `caffeinate -i -t 300` (pid 37177), a **child** of pid 23954 = `claude bg-spare`, the harness's own worker (an ancestor of the checker, hence `checker_ancestry`). The harness spawns it per tool call; it inherits the worktree cwd. `conduct/liveness.py:237-240` already documents this exact process | Fix the classifier at its base |

## Approach (two tasks, in order)

**Task 1 — classify the harness keep-awake child as checker-owned (limen code PR).**

- `cli/src/limen/process_ownership.py`, in the loop at ~line 319: after the `excluded` branch, treat a process as
  `{"category": "checker", "reason": "checker_keepawake"}` iff **all** hold: its parent pid is in `excluded`;
  `os.path.basename(argv[0]) == "caffeinate"`; the remaining argv is exactly `-i -t <positive int ≤ 300>`.
  Invocation shape is the evidence, mirroring `conduct/liveness.py`; no pid or name allowlist.
- `cli/tests/test_process_ownership.py`, using the existing `cohort` fixture shape
  (`ownership.Process(pid, ppid, uid, started, argv, env, cwd)`, `evaluate(excluded=…)`): one positive case and four
  negative controls that must stay `unknown`/blocking: (a) same argv but parent **not** in `excluded`;
  (b) parent in `excluded` but argv has other flags (`-s`, or `-t 99999`, or no `-t`); (c) a non-`caffeinate` child
  of an excluded parent; (d) `caffeinate` child of an excluded parent with cwd **outside** scope (already skipped).
  The negatives are the deliverable: the rule must not hide a real survivor.
- Branch `fix/closeout-checker-keepawake-20261019` from fresh `origin/main`; `bash scripts/verify-scoped.sh`
  (cli change implicates `pytest-cli`, ~12 min, serialized; the target-test file runs first via
  `scripts/run-pytest-hermetic.sh`); `scripts/merge-policy.sh` → merge the exact head.

**Task 2 — rebuild the owner receipt so the checker can pass (docs PR).**

- Fresh worktree/branch `docs/session-closeout-approval-audit-20261019-v2` from `origin/main` *after* Task 1 merges, so
  the checker run from that checkout carries the fix. Run the checker **from that checkout's `scripts/`**, with
  `--worktree` bound to the session's registered native worktree, not the shared checkout.
- Re-capture the three verification files at the new base head `X`; set both `base_head` and every
  `verification[].head` to `X` (precedent). `owned_paths` unchanged; the receipt commit touches only the receipt dir.
- Publish the branch, **run the predicate twice before merging** (the squash merge deletes the remote
  `publication_branch`, which is issue #2970's known limitation), quote both bare exit codes, then merge.
- Only if both exit 0: the terminal `CLOSEOUT COMPLETE` statement. A new finding after these fixes is a changed
  input, so one corrective retry is allowed; a third class of failure is recorded with its owner instead.

## Not doing (and why)

- Not attributing pid 37177 through a committed `process_ownership` packet: the pid changes every run.
- Not listing ~75 other sessions' paths as `retained_work`: unattributable from evidence, and the precedent shows the
  base should not span them.
- Not touching `base_head` semantics in the checker: its contract (`base_head` is an ancestor of `HEAD`) is sound;
  the fault was my choice of base.
- Not re-filing #2054/#2966/#2970: #2054 is the quota owner; #2966 is closed; #2970 stays the owner for
  squash-merge recognition.

## Verification

- Task 1: new test file section passes, including all four negative controls; `scripts/verify-scoped.sh` exit 0;
  `check-agent-docs`/`ruff` gates in the scoped run pass.
- Task 2: `bash scripts/no-tasks-on-me.sh … --json` exits 0 twice, second run creating nothing
  (`git status --short` empty before and after).
- Observed (not just predicate): the first measured pass happens from inside Claude Code's own shell, which is the
  case that failed.
