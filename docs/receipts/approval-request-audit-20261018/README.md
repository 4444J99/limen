# Approval-request audit — 72h to 2026-10-18T17:16Z

Owner: https://github.com/4444J99/limen/issues/3091

## Question

The operator reported that every approval request in the previous 70+ hours was inappropriate. This
receipt tests that against the written rules (CLAUDE.md litmus: *am I destroying, sending, spending, or
irreversibly leaking?*; AGENTS.md Session Discipline rule 1, derive answers; the Standing Autonomy
section) and names the base to fix for each cause.

## Method

- Window: records timestamped 2026-10-15T17:16Z onward across `.agent-runtime/claude/projects/*/*.jsonl`.
- Four visible approval traces: `AskUserQuestion`, `ExitPlanMode`, a rejected permission prompt
  ("doesn't want to proceed"), and an auto-mode classifier denial. 114 events, about 101 distinct moments
  (some are logged twice across session ids).
- 19 classifier agents judged each event against the rubric; two skeptics per batch (litmus lens, evidence
  lens) tried to refute every "inappropriate" label; two forensic agents read the settings layers; one
  synthesis agent clustered by root cause. All were read-only.
- The security warnings the runner raised on four subagents were checked against their tool calls: only
  `Read`, in-worktree `grep` and structured output. The flagged content is quoted transcript text inside
  the audited events, not subagent behavior.

## Result

| Kind | Events | Inappropriate | Borderline | Warranted |
|---|---|---|---|---|
| AskUserQuestion | 39 | 6 | 28 | 5 |
| ExitPlanMode | 17 | 7 | 9 | 1 |
| rejected permission prompt | 12 | 12 | 0 | 0 |
| classifier denial | 46 | 19 | 21 | 6 |
| **Total** | **114** | **44 (39%)** | **58 (51%)** | **12 (11%)** |

"Every single" is false: 12 stops were warranted (a public-visibility leak, a history purge needing
force-push and spend, a keychain probe, a PR body asserting an authorization the operator never gave, a
merge condition the operator set that was unmet, a staged raw inventory about to be pushed, a Touch ID read
needing presence). The modal prompt, though, was produced by a defect, not by risk.

**Direction caveat.** The adversarial pass challenged only "inappropriate" labels, so the 58 borderline and
12 warranted labels were never attacked: 44 is a floor. Approved prompts leave no transcript trace, so the
audit sees refusals, not the approvals the operator gave.

## Root causes and base fixes

| # | Cause (events) | Base | Owner / arming |
|---|---|---|---|
| 1 | The user-level runtime settings have `defaultMode: auto`, five `ask` rules and **no `permissions.allow`**; Limen's allow list lives only in each checkout's `.claude/settings.json`, so a session launched from `~` or another repo sends every command to the classifier (24) | `modify_private_settings.json.tmpl` in domus-genoma: an owned `permissions.allow` (read-only set plus the exact-head merge and `gh pr ready` rails) and a standing-grants slot in the autoMode environment | Agent authors the PR; operator names the widening and runs `chezmoi apply` (lever `L-APPROVAL-USER-ALLOW-WIDENING`) |
| 2 | `permissions.defaultMode: "plan"` in `.claude/settings.json` forces `ExitPlanMode` on every interactive session, including explicitly requested reversible work (16) | Remove the project default; rewrite CLAUDE.md "Session Phase Entry" so the agent enters plan mode only for a litmus hit or another session's work; update `check-agent-docs.py` in the same PR | Product decision the charter owns (lever `L-APPROVAL-PLAN-DEFAULT`) |
| 3 | Menus and re-asks where the charter or a registry already decides (23) | Extend `scripts/claude-workflow-guard.py audit-transcript` to flag a Recommended option that was accepted, a repeated question, and a menu after delegation | Agent PR; no arming |
| 4 | `/closeout` improvised `rm`, `python3 -I -c`, `shasum` and a job-tmp wrapper (14) | Closeout SKILL.md copies: probes via `mktemp` outside the worktree, `jq empty` / `shasum` / a checked-in helper, call `scripts/no-tasks-on-me.sh` directly; a grep gate over every copy | Agent PRs (limen, ai-skills, domus-genoma) |
| 5 | Charter silent on merge-past-red, what "override host" covers, over-cap suites (10) | CLAUDE.md lines plus a `gates.yaml` timeout for `pytest-cli` (#2898) | Agent PR |
| 6 | Leaky or opaque command forms (bare `env`, `~/.ssh` listing, transcript token grep); stops defensible (15) | Domus PreToolUse dispatcher reroutes plus `guard-liveness-check.sh` fixtures | Agent authors; operator arms with the cause-1 apply |
| 7 | Worktrees carry frozen copies of the project allowlist (38 of 58 live copies are pre-#3006) | Fold durable entries of the shared `settings.local.json` into tracked settings; a drift sensor in `sensors.yaml` | Agent PR (forward risk only) |

Hypothesis tested and refuted for the rejected-prompt incident: that a stale worktree allowlist caused it.
`Bash(shasum *)` reached main at 05:08:58Z, after both rejected prompts (04:58Z, 05:02Z), and the session's
cwd was the worktree itself. The stale-copy mechanism is real (cause 7) but did not cause that incident.

## Correction to PR #3088

PR #3088 (26 read-only allow entries) edits the **project** layer only. It does not reach sessions launched
outside a Limen checkout and does not reach the 38 worktrees holding older copies. Cause 1 is the larger
base.

## Unresolved

- Whether auto mode consults the classifier even for allowlisted commands (a denied `gh pr merge --match-head-commit`
  came from a session launched in `~` whose worktree allowed it). Discriminating test after arming: run one
  fixture from a session launched in `~` and one launched in a Limen checkout.
- Whether Claude Code honours the nested `permissions.autoMode.allow` block.
- Recorder for approved prompts: no `PermissionRequest` hook exists; add a Domus-owned append-only receipt
  hook, armed with the cause-1 apply.

## Next commands

Agent now (limen): the `audit-transcript` extension (cause 3), closeout SKILL text (4), charter lines (5).
Agent now (domus-genoma, staged, not applied): the cause 1 and 6 template diff, shown via `chezmoi diff`.
Operator: the two levers above.
