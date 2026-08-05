# Removal Acceptance Covenant

Local removal is a terminal action. Limen may inventory, classify, bridge,
preserve, and report roots autonomously, but it must not physically remove a
branch ref, clone, worktree, scratch root, or similar local root until the
removal surface has all of the following:

1. Loss-free classification by the owning tool.
2. Durable archive or remote-storage proof.
3. Redaction review proof for any private or sensitive payload.
4. Explicit human acceptance in the surface-specific JSONL ledger.

Every acceptance event must include non-empty `accepted_at`, `archive_proof`,
and `redaction_proof`. `accepted: true` is not sufficient without those proof
fields.

Do not create acceptance JSONL events as a cleanup shortcut. The JSONL ledgers
are evidence that a human accepted the exact storage, archival, redaction, and
ownership proof for a proposed removal.

## Standing grant — loss-free worktree class (2026-07-09)

The operator directed (2026-07-09, after the acceptance loop deadlocked at 646
pooled roots / ~38 GiB with `removed: []` on every beat) that the loss-free
worktree class is **pre-accepted for removal**: a root whose tree is clean,
whose HEAD is merged into the remote default branch or whose preservation
receipt proves a merged remote PR, and which is idle past its min-age.
`scripts/reclaim-worktrees.py` honors this as
`standing-grant-2026-07-09` (disable with
`LIMEN_RECLAIM_STANDING_ACCEPTANCE=0`). The classifier's own checks (dirty,
unpushed, active) remain the guardrails, and every removal is
still receipted in `logs/reclaim-worktrees.jsonl`. All other classes on every
surface still require a per-root human acceptance event.

**Merge-before-reap correction (2026-07-09).** The standing grant is merged-only.
A pushed branch or open PR is preservation, not closure. A root that is clean and
idle and whose commits are already on origin but are **not** merged is kept as
`not-merged-to-default`; the owning PR/task must be merged, or the reason it
cannot merge must be solved, before any local checkout is removed. The
`unpushed-commits` and `dirty` guardrails are unchanged — a root whose work is
not yet on origin is **never** reaped.

This standing grant does not apply to Antigravity/Agy scratch roots. Those roots
must use the `antigravity_scratch` surface and its archive/redaction acceptance
ledger, even when a generic worktree classifier can prove the clone is clean,
merged, and idle.

## Checked Surfaces

| Surface | Tool | Acceptance doc | Acceptance ledger | Terminal action |
|---|---|---|---|---|
| branch | `scripts/reap-branches.py` | `docs/branch-reap-acceptance.md` | `docs/branch-reap-acceptance.jsonl` | `git branch -D` |
| remote_branch | `scripts/reap-remote-branches.py` | `docs/remote-branch-reap-acceptance.md` | `docs/remote-branch-reap-acceptance.jsonl` | `git push origin --delete` (remote ref, not reflog-recoverable; double-dark: `LIMEN_REMOTE_REAP_APPLY=1`) |
| clone | `scripts/reap-clones.py` | `docs/clone-reap-acceptance.md` | `docs/clone-reap-acceptance.jsonl` | remove standalone clone root |
| worktree | `scripts/reclaim-worktrees.py` | `docs/worktree-reclaim-acceptance.md` | `docs/worktree-reclaim-acceptance.jsonl` | remove worktree or generated residue root |
| antigravity_scratch | `scripts/antigravity-scratch-bridge.py` | `docs/antigravity-scratch-reap-acceptance.md` | `docs/antigravity-scratch-reap-acceptance.jsonl` | remove Antigravity scratch root |

The checked source of truth for this table is
`scripts/reap_acceptance.py`. `scripts/check-removal-acceptance.py` verifies
that every registered surface has a tool, a doc, a ledger, shared proof-field
enforcement, and this covenant reference. `scripts/verify-whole.sh` runs that
predicate so future local-removal tools cannot silently drift out of the
archive/redaction/human-acceptance contract.
