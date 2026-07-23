# Worktree abandonment contract

`limen.worktree_abandonment.v1` is the sole physical recovery boundary used by
the worktree reaper. It records `planned`, `verified`, `applying`, `completed`,
or `crashed` state in a private atomic receipt.

- Clean registered linked worktrees are detached with Git's native non-forced
  worktree operation. The helper rechecks registration, HEAD, cleanliness, and
  process ownership before acting.
- Standalone clones, residue, ignored generated payloads, and dead-gitdir
  orphans are atomically renamed into a same-filesystem quarantine. Cross-device
  moves and destination collisions fail closed; no copy fallback is allowed.
- The stable-lock operation is restricted to the exact captured identity of a
  regular zero-byte file. It rechecks identity around an unprivileged owner
  probe and never follows symlinks.

`python3 scripts/worktree-abandonment.py` is dry-run by default. `--apply` is
required for a detach, quarantine move, or exact stable-lock removal. The helper
never resets a repository, cleans ignored files, or recursively deletes a path.
