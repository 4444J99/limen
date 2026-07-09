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
whose HEAD is merged into the remote default branch, and which is idle past
its min-age. `scripts/reclaim-worktrees.py` honors this as
`standing-grant-2026-07-09` (disable with
`LIMEN_RECLAIM_STANDING_ACCEPTANCE=0`). The classifier's own checks (dirty,
unpushed, active) remain the guardrails, and every removal is
still receipted in `logs/reclaim-worktrees.jsonl`. All other classes on every
surface still require a per-root human acceptance event.

**Pushed-is-enough (2026-07-09).** The operator's standing rule is "nothing is
deleted without being pushed to remote first" — so preservation, not merge, is
the bar. A root that is clean and idle and whose commits are already on origin
(`reachable_from_remote`) but is **not** merged is `clean+pushed+idle`: removing
the local checkout loses zero work (the branch remains on origin, resumable by
fetch+checkout), so it is pre-accepted under the same standing grant. Gated by
`LIMEN_RECLAIM_PUSHED_OK` (default on; set 0 for the conservative merged-only
gate). The `unpushed-commits` and `dirty` guardrails are unchanged — a root
whose work is not yet on origin is **never** reaped.

## Checked Surfaces

| Surface | Tool | Acceptance doc | Acceptance ledger | Terminal action |
|---|---|---|---|---|
| branch | `scripts/reap-branches.py` | `docs/branch-reap-acceptance.md` | `docs/branch-reap-acceptance.jsonl` | `git branch -D` |
| clone | `scripts/reap-clones.py` | `docs/clone-reap-acceptance.md` | `docs/clone-reap-acceptance.jsonl` | remove standalone clone root |
| worktree | `scripts/reclaim-worktrees.py` | `docs/worktree-reclaim-acceptance.md` | `docs/worktree-reclaim-acceptance.jsonl` | remove worktree or generated residue root |
| antigravity_scratch | `scripts/antigravity-scratch-bridge.py` | `docs/antigravity-scratch-reap-acceptance.md` | `docs/antigravity-scratch-reap-acceptance.jsonl` | remove Antigravity scratch root |

The checked source of truth for this table is
`scripts/reap_acceptance.py`. `scripts/check-removal-acceptance.py` verifies
that every registered surface has a tool, a doc, a ledger, shared proof-field
enforcement, and this covenant reference. `scripts/verify-whole.sh` runs that
predicate so future local-removal tools cannot silently drift out of the
archive/redaction/human-acceptance contract.
