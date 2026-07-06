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
