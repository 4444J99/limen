# Storage Creep Receipt - 2026-07-05

This receipt records the live storage closeout from the 2026-07-05 Limen healing session. It is an
owner surface for the local-lifecycle disk-pressure blocker; it does not authorize blind deletion of
personal data stores or agent scratch roots.

## Live Footprint

- Internal data volume: `460Gi` size, `406Gi` used, `25-26Gi` available, `95%` capacity.
- Archive4T: `3.6Ti` size, `523Gi` used, `3.0Ti` available.
- `~/.gemini`: about `33G`; `~/.gemini/antigravity-cli`: about `32G`.
- `~/.gemini/antigravity-cli/scratch`: about `31G`.
- Largest Antigravity scratch roots observed:
  - `session-meta`: `4.7G`
  - `organvm-session-meta`: `4.7G`
  - `session-meta-2`: `4.5G`
  - `session-meta-no-prompt`: `4.5G`
  - `peer-audited--behavioral-blockchain`: `2.2G`
  - `sovereign-systems--elevate-align`: `1.2G`
  - `public-record-data-scrapper`: `1.0G`
  - `growth-auditor`: `972M`
- `~/Workspace` remains large, but the Limen-owned loss-free cleanup path did not find meaningful
  immediate reclaim this run.

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

## Decision

Do not delete `~/Library/Messages`, Notes/Freeform/iCloud/Mail/Photos stores, or
`~/.gemini/antigravity-cli/scratch` blindly.

The next real storage fix is a new Agy/Antigravity scratch bridge:

1. Inventory each scratch root.
2. Prove whether it has a git remote, clean status, PR/commit receipt, or explicit owner blocker.
3. Preserve unique deltas to the owning repo or Archive4T with a receipt.
4. Reap only roots that are either pure pushed mirrors or archived with verification.

Until that bridge exists, the current large reclaim candidate is known but intentionally parked:
`~/.gemini/antigravity-cli/scratch` is the major local creep source and needs proof before removal.
