# Prompting a live Claude session from another lane

A non-Claude peer (Codex, Gemini, OpenCode, ...) has no `SendMessage` tool. Two tempting routes are
closed on purpose, and neither is to be bypassed:

| Route | Why it is closed |
|-------|------------------|
| Computer Use on a terminal app (Ghostty, Terminal, iTerm) | The harness denies terminal apps for safety. Keystroke injection by tmux or AppleScript is the same door. |
| `claude ...` run from `~` or any non-repo cwd | The host admission rail (`domus-claude-host-hook` -> `action_admission.py`) admits Claude mutations only from a **linked git worktree**. `worktree_scope()` in `cli/src/limen/host_admission.py` raises `workspace-scope-unavailable` otherwise. |

## Two gates, two cwds

There are two admission decisions, and they look at different checkouts:

1. **The caller's hook** judges the shell command the caller runs. Any command it cannot classify is a
   workspace mutation, so it demands a linked-worktree cwd and a writer lease from the *caller*. A
   caller in `~` is denied with `workspace-scope-unavailable` before Python starts. Nothing the script
   does with its child's cwd can reach this decision.
2. **The target's hook** judges the `claude --bg --resume` child. The child runs from the target's own
   linked worktree, so that decision passes.

Gate 1 is why `prompt-claude-session.py` is registered in `_SANCTIONED_SCRIPTS`
(`cli/src/limen/action_admission.py`), beside `dispatch-async.py` and `host-work-admission.py`: it
mutates no workspace of the caller's, and it carries its own safety checks (below). The recognised
form is `python3 scripts/prompt-claude-session.py ...`; a bare shebang invocation is not sanctioned.

## The path

```
python3 scripts/prompt-claude-session.py --to "<session name | id | unique prefix>" --prompt-file <file | -> [--dry-run] [--receipt PATH]
```

1. Resolves the target from `claude agents --json`. Ambiguous or missing is a refusal, never a guess.
2. Refuses anything that is not a `background` session. Interactive sessions belong to a human.
3. Re-reads the target's row immediately before sending and refuses a `busy` target. `claude --bg
   --resume` on a running session forks a copy and splits ownership; `--allow-copy` is the explicit
   opt-in. A per-target lock stops two concurrent senders from racing each other.
4. Refuses a target whose `cwd` is missing, relative, not a git checkout, or the shared checkout. The
   target's `cwd` is never defaulted: an absent value would otherwise validate the caller's checkout.
5. Runs `claude --bg --resume <sessionId> -- <prompt>` with **cwd = the target's own linked worktree**,
   using the same `worktree_scope()` the hook uses, so the script and the rail cannot disagree.
6. Lists sessions again and compares: the receipt records `forked`, `identity_verified` and
   `receiving_session`. A new session that appeared during the send is a fork, and a fork the caller
   did not ask for is not reported as delivered.
7. Prints a JSON receipt (prompt sha256 and size, never the prompt body). `acknowledged` is always
   `false`: read the reply with `claude logs <id>`.

Exit codes: `0` delivered and receiver verified (or dry run), `2` refused before sending, `3` `claude`
failed or timed out (delivery unknown), `4` sent but the receiver could not be verified or a fork
received it.

## Limits

- The prompt travels as a `claude` argument, so it is visible to `ps` for the duration of the send on
  this host. The script never stores or prints it: the receipt, `claude`'s captured output, and every
  error path are scrubbed, and a timeout reports the fact, not the exception (which embeds the command).
- Verification is by session listing, not by the receiver's say-so. The window between the
  re-read and the send is narrowed, not closed: a target that turns busy inside it is caught after the
  fact (`forked`, exit `4`), not prevented.
- A target whose cwd is the shared checkout is refused: the rail would deny it there too.
- This delivers a prompt; it does not make the receiver agree to act. The receiving session's own
  permission mode and the Peer Conductor Contract still govern what it does with it.
- Work that should be tracked as a task goes through `limen conduct submit`, not through this path.
