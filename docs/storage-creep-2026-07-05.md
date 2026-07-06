# Storage Creep Receipt - 2026-07-05

This receipt records the live storage closeout from the 2026-07-05 Limen healing session. It is an
owner surface for the local-lifecycle disk-pressure blocker; it does not authorize blind deletion of
personal data stores or agent scratch roots.

## Live Footprint

- Internal data volume: `460Gi` size, `403Gi` used, `28Gi` available, `94%` capacity after the
  2026-07-06 safe reaps.
- Archive4T: `3.6Ti` size, `523Gi` used, `3.0Ti` available.
- `~/.gemini`: about `30G`; `~/.gemini/antigravity-cli`: about `30G`.
- `~/.gemini/antigravity-cli/scratch`: about `28G`.
- Largest Antigravity scratch roots observed before the safe reap:
  - `session-meta`: `4.7G`
  - `organvm-session-meta`: `4.7G`
  - `session-meta-2`: `4.5G`
  - `session-meta-no-prompt`: `4.5G`
  - `peer-audited--behavioral-blockchain`: `2.2G`
  - `sovereign-systems--elevate-align`: `1.2G`
  - `public-record-data-scrapper`: `1.0G`
  - `growth-auditor`: `972M`
- `~/Workspace` remains large, but Limen-owned cleanup now has proof-backed reapers for pure mirrors,
  generated worktree log shells, and clean remote-merged preservation receipts.

## Owner-Safe Reclaim Check

- `python3 scripts/cvstos-organ.py` reported only `0.22GB evictable / 2.13GB retained` across its
  current allowlisted chat-app caches.
- `LIMEN_RECLAIM_DRYRUN=1 LIMEN_CLONE_REAP_APPLY=0 LIMEN_BRANCH_REAP_APPLY=0 bash scripts/clone-maintenance.sh`
  reported:
  - `node_modules: 0 dir(s) would free 0.00 GB`
  - `would reap 0 clone(s), 0.00 GB`
  - two landed local branches, which were reaped separately by `scripts/reap-branches.py --apply`.
- `python3 scripts/worktree-debt.py --json` still reports worktree debt, but current debt is mostly
  non-git scratch roots or owner-blocked/live-work roots, not loss-free cache.

## 2026-07-06 Update

- The Agy/Antigravity scratch bridge now exists: `scripts/antigravity-scratch-bridge.py`.
- `python3 scripts/antigravity-scratch-bridge.py --write` produced
  `docs/antigravity-scratch-bridge.md` and measured `66` scratch roots, `30.6 GiB` total, with
  `2.2 GiB` marked `safe_reap_candidate`.
- `python3 scripts/antigravity-scratch-bridge.py --write --apply-safe-reap` reclassified each
  candidate immediately before deletion, then reaped `23` clean remote-preserved roots, reclaiming
  `2.2 GiB` with `0` skipped and `0` failed. Post-reap scratch size: `28.4 GiB` across `43` roots.
- Scratch deletion is still not authorized by size alone. The same receipt found `34`
  `bridge_required` roots plus container/non-git/preserve review roots; those require owner-proof or
  delta preservation before local removal.
- CVSTOS now surfaces Antigravity scratch health through `LIMEN_AGY_SCRATCH_ROOT` and
  `LIMEN_AGY_SCRATCH_MIN_IDLE_H`, so unsafe scratch dispositions become part of the regular
  proprioception signal instead of a one-off storage note.
- The generated worktree log-shell residue class was made mechanically reclaimable and then reaped:
  `LIMEN_RECLAIM_MAX=100 python3 scripts/reclaim-worktrees.py --apply --force` removed `53` exact
  generated log-shell roots.
- `scripts/reclaim-worktrees.py` now accepts a clean+idle `remote-merged` preservation receipt as
  lifecycle proof when the receipt has `pr_state: MERGED`, a durable PR URL, and no private patch
  marker.
- `python3 scripts/reclaim-worktrees.py --apply --force` reaped another `7` clean receipt-backed
  completed roots: `pr-463`, `pr-466`, `pr-467`, `pr-468`, `pr-471`, `pr-475`, and
  `GEN-organvm-limen-ci-green-0702`.
- Post-reap predicates are tighter: `python3 scripts/worktree-debt.py --json` now reports `debt: 1`
  across `29` targets, and `python3 scripts/reclaim-worktrees.py --force` reports
  `0 reclaimed, 29 kept-safe`.

## Decision

Do not delete `~/Library/Messages`, Notes/Freeform/iCloud/Mail/Photos stores, or
`~/.gemini/antigravity-cli/scratch` blindly.

The next real storage fix is to act through the Agy/Antigravity scratch bridge:

1. Inventory each scratch root.
2. Prove whether it has a git remote, clean status, PR/commit receipt, or explicit owner blocker.
3. Preserve unique deltas to the owning repo or Archive4T with a receipt.
4. Reap only roots that are either pure pushed mirrors or archived with verification.

The remaining large reclaim candidate is known but intentionally parked behind proof:
`~/.gemini/antigravity-cli/scratch` is still the major local creep source, and further removal should
proceed only from future `safe_reap_candidate` roots or from roots whose dirty/preserve blockers have
been bridged into their owner repository or an Archive4T receipt.
