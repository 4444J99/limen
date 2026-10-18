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
