# Fewer permission prompts — allowlist additions

## Context

`/fewer-permission-prompts` scans recent transcripts for read-only Bash and MCP calls that still
prompt, and adds narrow allow rules to the project `.claude/settings.json`. Scan scope: the 50
most-recently-modified `*.jsonl` transcripts under
`/Users/4jp/Workspace/limen/.agent-runtime/claude/projects/*/` (all projects, including worktree
sessions). Counts below are approximate: the command tokenizer splits on `&&`, `;`, `|` and newlines,
so heredoc bodies add noise.

Most of the high-volume traffic needs no rule, because Claude Code already auto-allows it:
`git` (1622), `grep` (1239), `ls`, `head`, `sed`, `jq`, `wc`, `tail`, `sort`, `du`, `df`, `stat`,
`which`, `date`, `ps`, `pgrep`, `find`, `xargs`, `echo`, `gh pr view/list/diff/checks`,
`gh issue view/list`, `gh repo view`.

## Proposed additions to `permissions.allow` (merge only — nothing removed or reordered)

| # | Pattern | ~Count | Why it is read-only |
|---|---------|-------:|---------------------|
| 1 | `Bash(python3 scripts/host-work-admission.py status *)` | 71 | writer-lease / capacity status (`--no-probe` is the usual form); pinned script + subcommand, same precedent as the existing `scripts/gitvs.py *` rule |
| 2 | `Bash(python3 scripts/host-work-admission.py status)` | 2 | bare form of #1 |
| 3 | `Bash(python3 scripts/host-work-admission.py capabilities)` | 3 | prints a capability document |
| 4 | `Bash(python3 scripts/host-work-admission.py --help)` | 7 | usage text |
| 5 | `mcp__claude-in-chrome__list_connected_browsers` | 13 | lists attached browsers |
| 6 | `Bash(chezmoi diff *)` | 28 | source-vs-target diff (Rule #10 pre-check before any `chezmoi add`) |
| 7 | `Bash(shasum *)` | 18 | checksums for receipts; `sha256sum` is auto-allowed but `shasum` is not |
| 8 | `Bash(bash scripts/run-pytest-hermetic.sh *)` | 14 | hermetic pytest wrapper; `python3 -m pytest *` is already allowed |
| 9 | `Bash(bash /Users/4jp/Workspace/limen/scripts/merge-policy.sh *)` | 13 | absolute-path form of the already-allowed `merge-policy.sh` predicate |
| 10 | `Bash(claude --version)` | 12 | version string |
| 11 | `Bash(claude plugin list *)` | 10 | lists installed plugins |
| 12 | `Bash(chezmoi source-path *)` | 11 | prints a path |
| 13 | `Bash(chezmoi managed *)` | 9 | lists managed files |
| 14 | `Bash(/Users/4jp/.local/bin/domus-limen-runtime verify-heartbeat *)` | 7 | help text: "verify the installed one-shot heartbeat and its exact runtime receipt" |
| 15 | `Bash(/Users/4jp/.local/bin/domus-limen-runtime plan-heartbeat *)` | 9 | help text: "review an exact merged heartbeat contract **without host mutation**" |
| 16 | `Bash(/Users/4jp/.local/bin/domus-limen-runtime status *)` | 3 | status report |
| 17 | `Bash(scripts/verify-scoped.sh *)` | 4 | direct-exec form of the already-allowed `bash scripts/verify-scoped.sh *` |
| 18 | `mcp__claude-in-chrome__get_page_text` | 5 | reads page text |
| 19 | `mcp__ccd_session_mgmt__list_sessions` | 3 | lists sessions |
| 20 | `mcp__ccd_pr__get_status` | 3 | PR status read |

## Skipped, with reasons

- **Already auto-allowed** (no rule needed): `git *` reads, `grep`, `ls`, `head`, `tail`, `sed`, `jq`,
  `wc`, `sort`, `du`, `df`, `stat`, `which`, `date`, `ps`, `pgrep`, `find`, `xargs`, `echo`,
  `gh pr view/list/diff`, `gh repo view`.
- **Already in the allowlist**: `git fetch/push/add/commit/switch/worktree`, `gh api *`, `gh run list/view`,
  `gh issue list/view`, `gh pr merge/create`, `sqlite3 *`, `npm *`, `bash scripts/verify-scoped.sh *`,
  `bash scripts/merge-policy.sh *`, `mkdir *`, `chmod +x *`.
- **Arbitrary code execution — never allowlisted**: `python3`, `cli/.venv/bin/python`, `uv run`, `uvx`,
  `just`, `bash`/`/bin/bash` wildcards, the Antigravity/Chrome app binaries.
- **Not read-only or unverified**: `host-work-admission.py acquire/release/diagnose`,
  `domus-limen-runtime install/prune/activate-heartbeat/retire-heartbeat/producer-exec`,
  `vendor-insights.py index` (may write a cache), `limen conduct *` (mixed read and write subcommands),
  `curl` (can POST or egress with appended flags), `gh repo clone`, `chezmoi apply`, `git push` variants.
- **MCP not added**: `claude-in-chrome__javascript_tool` (61, arbitrary page JS), `__computer` (24, drives
  clicks/typing), `__navigate`, `__tabs_create_mcp`, `__tabs_close_mcp` (change browser state);
  `mcp__ccd_turn__*` / `__session__*` (session UI plumbing, writes); `mcp__github__*_write/_comment` (writes).

## Implementation (after approval)

1. Edit `.claude/settings.json` in this worktree (`worktree-chore-fewer-permission-prompts-20261018`):
   append the 20 entries above to `permissions.allow`, after the existing last entry. Touch no other key.
2. Validate: `jq empty .claude/settings.json` must exit 0, and a `jq` duplicate check on
   `permissions.allow` (`group_by(.) | map(select(length>1))`) must print `[]`.
3. Commit and ship through the chore rail: `scripts/verify-scoped.sh`, push, open the PR, then
   `scripts/merge-policy.sh <PR#>` and merge on exit 0 (not website-sensitive; `.claude/settings.json`
   is not a deploy-trigger path).
4. Report counts and the skip list back to the user.

Note: this change touches `permissions.allow` only, not hooks or `defaultMode`, so it stays clear of the
self-modification boundary the charter reserves for hook-arming.

## Verification

- `jq empty` and the duplicate check above, run on the edited file.
- `git diff` shows only added lines inside the `allow` array.
- `scripts/verify-scoped.sh` runs clean; it names whatever gates a `.claude/settings.json` change implicates.
- Live proof: in a fresh session, `python3 scripts/host-work-admission.py status --no-probe` runs
  without a permission prompt.
