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
| 1 | The user-level runtime settings have `defaultMode: auto`, five `ask` rules and **no `permissions.allow`**; Limen's allow list lives only in each checkout's `.claude/settings.json`, so a session launched from `~` or another repo sends every command to the classifier (24) | Repair the operator-armed effector `scripts/heal-hook-wiring.py`: it still targets the retired `private_dot_claude/settings.json.tmpl`, while the live source is the split-ownership Python script `modify_private_settings.json.tmpl`, which owns `env`, `permissions.ask`, `hooks`, `autoMode` and no `permissions.allow`. Extend its dry-run-by-default assertions to the read-only command classes. **Do not author the diff in domus-genoma**: `docs/never-hang-permission-spec.md` makes the act, not the path, the classifier boundary | Agent repairs and merges the effector dry-run only; the operator reads the diff and decides to run `--apply` (lever `L-APPROVAL-USER-ALLOW-WIDENING`; its step 2, which says an agent authors a domus-genoma PR, predates this correction and is superseded by this row) |
| 2 | `permissions.defaultMode: "plan"` in `.claude/settings.json` forces `ExitPlanMode` on every interactive session, including explicitly requested reversible work (16) | **Decided by protocol: keep.** CLAUDE.md "Session Phase Entry" says not to replace plan-mode entry with an auto-mode entry, and names the exit (shift+tab, or ExitPlanMode). The ceremony is the designed price; it is measured by the transcript audit, not removed | Answered by protocol. Lever `L-APPROVAL-PLAN-DEFAULT` was filed before this derivation and awaits the operator's closure, since atoms are closed only by the human |
| 3 | Menus and re-asks where the charter or a registry already decides (23) | Extend `scripts/claude-workflow-guard.py audit-transcript` to flag a Recommended option that was accepted, a repeated question, and a menu after delegation | Agent PR; no arming |
| 4 | `/closeout` improvised `rm`, `python3 -I -c`, `shasum` and a job-tmp wrapper (14) | The skill left receipt checking unspecified. **Landed in #3097** (limen copy): step 2 now names `jq empty`, the committed blob id, and `mktemp -d` probes outside the worktree. The proposed grep gate is not built: the limen skill text never contained those commands. The ai-skills and domus-genoma copies are other repositories and are unchecked | Done for limen; other copies owed |
| 5 | Charter silent on merge-past-red, what "override host" covers, live-edit overwrite (10) | **No charter change: protocol already decides each case.** `pytest-cli`'s timeout is already fixed (#2965, `f1297a8bf`; the 1500s registry budget is honored) and #2898 stays open only for the keeper verification window. "Override host" (E059, the operator's words "override host and get this gd job done", said while the heavy slot was held by a soak) means overriding the host's admission hold, never skipping a gate, because AGENTS.md says no rung may be skipped to manufacture a pass ("Green is additive"). Merge-past-red (E056): the agent's own option "fix the red test first" is the derivable answer, and it then did that in #2938. Overwriting live out-of-band edits: Universal Rule 10 already requires a diff preview and confirmation. These were agent-behavior menus, so they join the cause 3 fixtures | None; the detector (cause 3) covers it |
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

Done: closeout skill text for limen (cause 4, #3097).
Derived by the decision cascade (protocol, then precedent, then exploration), with no operator input needed:
causes 2 and 5 are answered by existing protocol, so nothing is owed to the operator there beyond closing
`L-APPROVAL-PLAN-DEFAULT`.
Agent now (limen): the `audit-transcript` extension (cause 3), with fixtures for the cause 5 events
(E056, E060, E009) and the cause 3 events.
Agent now (limen): repair `scripts/heal-hook-wiring.py` to the live `modify_` source and extend it (causes 1 and
6), dry-run by default, merged unarmed.
Operator (the one irreducible act): read the repaired effector's dry-run diff and decide whether to run it
with `--apply` (lever `L-APPROVAL-USER-ALLOW-WIDENING`).
