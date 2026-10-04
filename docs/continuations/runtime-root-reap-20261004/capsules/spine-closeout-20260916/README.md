# Continuation capsule: spine-closeout-20260916

This README is the initial prompt index, not a concatenated brief. Before acting, read these local
modules in order:

1. `.limen-workstream/manifest.md` — historical location and custody snapshot;
2. `.limen-workstream/workstream.json` — validated runway, conductor, and authorization contract;
3. `.limen-workstream/intent.md` — objective and owner-specific context;
4. `.limen-workstream/runtime.md` — live probes and boundary decision contract;
5. `.limen-workstream/closeout.md` — receipt and successor rules.

Resolve them from `/Users/4jp/Workspace/limen/.worktrees/spine-closeout-20260916`. Missing, unreadable, stale, or contradictory modules make the capsule
invalid; stop rather than guessing. The intent fixes scope. Live evidence determines the lane and
ending.

The private capsule remains local and ignored. Its tracked redacted custody receipt is
`docs/continuations/spine-closeout-20260916/workstream.json`; the first launched session commits and pushes that receipt after admission.
The kickstart acquires the capsule lock and validates `.limen-workstream/capsule.identity`
plus that receipt before it admits the runway or launches a provider.

## Host-shell-only launch command

Run this command exactly once from the host shell. A provider launched by it is already admitted
and must continue from the modules above without executing this operator command.

```bash
bash "/Users/4jp/Workspace/limen/.worktrees/spine-closeout-20260916/.limen-workstream/kickstart.sh"
```

For a plain shell, use `cd "/Users/4jp/Workspace/limen/.worktrees/spine-closeout-20260916"` and then `${SHELL:-/bin/zsh} -l`.
