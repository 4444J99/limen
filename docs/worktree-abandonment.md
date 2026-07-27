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
- The sole destructive exception is `purge-proven-path`: the reclaimer may use
  it only for an exact `custody-restored+idle` candidate with full external
  restoration or a clean clone whose exact HEAD remains reachable from a remote
  ref. Path identity, proof, and active ownership are revalidated immediately
  before apply. The helper atomically isolates the exact directory, unlinks it
  without following symlinks, and records every phase in the abandonment receipt.
- The stable-lock operation is restricted to the exact captured identity of a
  regular zero-byte file. It rechecks identity around an unprivileged owner
  probe and never follows symlinks.

`python3 scripts/worktree-abandonment.py` is dry-run by default. `--apply` is
required for a detach, quarantine move, or exact stable-lock removal. The
proven purge has no free-standing CLI entrypoint: only the exact-SHA reclaimer
can invoke it. The helper never resets a repository or cleans ignored files.
