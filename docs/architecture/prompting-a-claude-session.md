# Prompting a live Claude session from another lane

A non-Claude peer (Codex, Gemini, OpenCode, ...) has no `SendMessage` tool. Two tempting routes are
closed on purpose, and neither is to be bypassed:

| Route | Why it is closed |
|-------|------------------|
| Computer Use on a terminal app (Ghostty, Terminal, iTerm) | The harness denies terminal apps for safety. Keystroke injection by tmux or AppleScript is the same door. |
| `claude ...` run from `~` or any non-repo cwd | The host admission rail (`domus-claude-host-hook` -> `action_admission.py`) admits Claude mutations only from a **linked git worktree**. `worktree_scope()` in `cli/src/limen/host_admission.py` raises `workspace-scope-unavailable` otherwise. |

## The path

```
scripts/prompt-claude-session.py --to "<session name | id | unique prefix>" --prompt-file <file | -> [--dry-run] [--receipt PATH]
```

1. Resolves the target from `claude agents --json`. Ambiguous or missing is a refusal, never a guess.
2. Refuses anything that is not a `background` session. Interactive sessions belong to a human.
3. Refuses a `busy` target. `claude --bg --resume` on a running session forks a copy and splits
   ownership; `--allow-copy` is the explicit opt-in.
4. Runs `claude --bg --resume <sessionId> -- <prompt>` with **cwd = the target's own linked worktree**,
   using the same `worktree_scope()` the hook uses, so the script and the rail cannot disagree.
5. Prints a JSON receipt (prompt sha256 and size, never the prompt body). `acknowledged` is always
   `false`: read the reply with `claude logs <id>`.

Exit codes: `0` delivered, `2` refused before sending, `3` `claude` failed.

## Limits

- A target whose cwd is the shared checkout is refused: the rail would deny it there too.
- This delivers a prompt; it does not make the receiver agree to act. The receiving session's own
  permission mode and the Peer Conductor Contract still govern what it does with it.
- Work that should be tracked as a task goes through `limen conduct submit`, not through this path.
