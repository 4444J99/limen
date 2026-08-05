# Linked-worktree growth admission

Every lane-neutral pre-tool write admission performs a bounded, read-only scan of the linked
worktree before acquiring its writer lease. The scan emits the in-memory
`limen.growth_admission.v1` decision shape and fails closed when it cannot prove all of these limits:

- no new UTF-8 text file exceeds 8 MiB;
- aggregate Git-untracked, non-ignored text does not exceed 64 MiB;
- at most 10,000 filesystem paths are needed to inspect the worktree; and
- no nested Git repository exists below the linked-worktree root.

The root worktree's own `.git` file or directory is authority, not a nested-repository violation.
Symlinks are never followed by the path walk, binary samples containing NUL or invalid UTF-8 do not
count toward text limits, and exactly-at-limit state remains admissible.

For structured writes whose payload exposes `content`, admission accounts for a not-yet-created
target before the write. Other mutation-capable tools are admitted only while the current bounded
snapshot is green; if a write crosses a limit, every subsequent write is denied. Denial never
deletes, truncates, resets, cleans, or otherwise repairs the offending paths. Observation remains
available so an owner can inspect and route a sanctioned recovery.
