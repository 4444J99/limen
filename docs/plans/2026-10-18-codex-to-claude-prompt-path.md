# Codex -> Claude session prompt path

Issue: #3005
PR: #3017

## Context

Codex was asked to babysit the Claude session **"external session review"** and could not deliver
an instruction. Two independent gates blocked it:

1. **`claude` CLI under the host hook** -> `workspace-scope-unavailable`. `worktree_scope()`
   (`cli/src/limen/host_admission.py:186-214`) raises it when `git rev-parse` cannot resolve a
   repo from the *caller's* cwd. The admission rail admits Claude mutations only from a linked
   worktree, so Codex running from `~` or a non-repo dir is denied by design.
2. **Computer Use -> Ghostty** is denied for safety (terminal apps are blocklisted). Not a bug;
   not to be bypassed (no tmux/AppleScript into the terminal either).

Both gates are compliant to route around. `SendMessage` exists inside Claude Code only, so Codex
cannot use it. Codex needs a path built from what Codex *can* call: a shell command.

## What already exists (verified this session)

- `claude agents --json` lists live sessions with `id`, `sessionId`, `name`, `cwd`, `kind`
  (`background`/interactive), `status` (`idle`/`busy`). Target "external session review" had
  `cwd=.../.claude/worktrees/front-door-gaps-20261018`, a **linked worktree** -> passes the hook.
- `claude --bg --resume <session-id> "<prompt>"` continues a background session under the same ID
  (or starts a *copy* and says so if it is already running). `claude logs <id>` reads its output.
- Prior art for non-interactive Claude launch: `dispatch.py` (`claude -p`, validated
  `--permission-mode dontAsk` for fleet lanes).

## Approach: `scripts/prompt-claude-session.py` (agent-neutral)

One bare command Codex (or any lane) runs:

```
scripts/prompt-claude-session.py --to "external session review" --prompt-file <file> [--json]
```

Behaviour, in order:
1. **Resolve** the target from `claude agents --json` by exact name, else id/sessionId prefix.
   Ambiguous or missing -> exit non-zero with the candidates listed (no guessing).
2. **Refuse protected targets**: interactive/human sessions are never prompted (Peer Conductor
   Contract: autonomous peers must not retune human sessions). Background sessions only.
3. **Refuse a busy target** by default, because `--bg --resume` on a running session forks a copy
   and splits ownership. Idle target: proceed. `--allow-copy` is the explicit opt-in to fork.
4. **Run `claude` with `cwd` = the target's own worktree** (read from the JSON), so the host hook's
   `worktree_scope()` resolves. If that cwd is not a linked worktree, fail with the exact reason
   rather than dropping into the shared checkout.
5. Deliver with `claude --bg --resume <sessionId> -- <prompt>`; the prompt is read from a file or
   stdin (never argv-interpolated through a shell) so multi-line instructions survive.
6. **Emit a receipt** (JSON: target id/name, prompt sha256, exit code, `claude logs` tail pointer)
   to stdout and `logs/`; delivery is not acknowledgement, and the script says so.

It does not touch Ghostty, Computer Use, or the hook; it satisfies the hook's own contract.

## Files

- New: `scripts/prompt-claude-session.py`, `cli/tests/test_prompt_claude_session.py`
  (resolution, busy/protected refusal, cwd selection; `claude` subprocess faked).
- New: `docs/architecture/prompting-a-claude-session.md` (the route, the closed doors, the limits).
- **Deviation from the approved draft:** no `AGENTS.md` pointer. It is already 33,765 B against the
  32,768 B instruction-surface budget (check S), so growing it is wrong; the doc plus `--help` carry it.
- **Deviation:** the receipt goes to stdout and an optional `--receipt PATH`, not an automatic
  `logs/` write (no new local-only state).
- The test lives under `cli/tests/`, which the existing pytest gate already globs.

## Verification

1. `python3 -m pytest cli/tests/test_prompt_claude_session.py -q` (read its own exit code).
2. `scripts/verify-scoped.sh` on the exact tree.
3. Live, runtime-observed: dry-run (`--dry-run`) against an idle bg session prints the resolved
   target, cwd and argv without sending; then one real send to an idle session and read
   `claude logs <id>` to confirm it drained. Report merged / live / observed separately.

## Out of scope

Loosening `host_admission.py`; keystroke injection into Ghostty; any Codex-side change to
Computer Use policy; re-sending the original review instruction (the target now reports `busy`,
so it is likely already working; the script's busy refusal covers a repeat).

## Review amendments (PR #3017 review, head dd322fd7)

Five findings, each dispositioned; the original approach's central claim was wrong.

- **P1 accepted — the original blockage remained.** Codex's dry-run was denied by *its own* hook
  (`admit_pre_tool_action`) before Python started: an unclassified command is a workspace mutation, so the
  caller needs a linked-worktree cwd and a writer lease. Setting the child's cwd cannot reach that
  decision. Fix: register the helper in `_SANCTIONED_SCRIPTS` (`action_admission.py`), the class
  `dispatch-async.py` and `host-work-admission.py` already belong to. **Deviation from "out of scope":** this
  edits `action_admission.py`, not `host_admission.py`, and adds one allow-list entry; the helper keeps
  its own safety checks. The recognised form is `python3 scripts/prompt-claude-session.py`; the earlier
  bare-shebang usage line is withdrawn. Evidence: before the change `classify_action` returns
  `workspace_write` for both forms; the admission suite now pins the `python3` form allowed from a
  non-repo cwd with no lease, and the bare form still denied.
- **P1 accepted — timeout exposed the prompt.** `str(TimeoutExpired)` embeds argv. The timeout is now a
  receipt (`delivered: false`, delivery unknown, exit 3); `main` never prints an exception string;
  captured `claude` output is scrubbed of the prompt.
- **P1 accepted — missing cwd selected the caller's checkout.** An absent or relative target cwd is a
  refusal, never `Path(".")`.
- **P1 accepted, residual stated — busy race and receiver identity.** The row is re-read right before the
  send, senders are serialized per target, and sessions are re-listed afterwards: the receipt records
  `forked`, `identity_verified`, `receiving_session`. The window is narrowed, not closed; a fork is
  detected after the fact (exit 4), not prevented.
- **P2 accepted — gate omitted the script.** New `prompt-claude-session-test` row in `gates.yaml`.

Observed-live verification (a real idle send and `claude logs` read-back) is recorded on the PR, not
here, because it can only happen after the head is pushed.
