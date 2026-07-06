# Deletion Surface Audit - 2026-07-06

Ground rule: nothing gets physically deleted merely because it looks old, merged,
regenerable, or temporary. Removal needs archive/storage proof and redaction proof,
or it stays a census candidate.

This audit records the state after the deletion-safety hardening pass. It is not an
acceptance ledger and does not authorize cleanup. The active acceptance ledgers remain:

- `docs/worktree-reclaim-acceptance.jsonl`
- `docs/branch-reap-acceptance.jsonl`
- `docs/clone-reap-acceptance.jsonl`
- `docs/antigravity-scratch-reap-acceptance.jsonl`

## Hardened Surfaces

These surfaces no longer perform direct branch/root/cache deletion:

| Surface | Previous behavior | Current behavior |
| --- | --- | --- |
| `scripts/cells.sh` | `cell reap` removed worktree, branch, pid/logs; `--force` discarded | `--force` retired; clean/preserved cells are delegated to reclaim/reap ledgers |
| `scripts/quicken.py` | closeout could remove worktrees/branches directly | closeout records delegated candidates only |
| `scripts/jules-land.py` | PR landing force-removed local worktree and branch | local root/branch are retained after PR creation |
| `cli/src/limen/dispatch.py` | local dispatch cleanup removed isolated roots/branches | dispatch classifies and retains roots/branches for later accepted reclaim |
| `scripts/ship-docs.sh` | trap removed local worktree/branch and merge deleted remote branch | local root plus local/remote branch are retained |
| `scripts/merge-ready.sh` / `scripts/merge-drain.py` | merge commands used `--delete-branch` | merges preserve source branches |
| `scripts/done-insight-cadence.sh` | predicate reset live insight logs/state | predicate writes to a retained verification sandbox |
| `scripts/done-session-orient.sh` | predicate removed temp verification fixtures | predicate retains tiny verification fixtures |
| `scripts/clone-maintenance.sh` | directly removed `node_modules` | reports reclaimable `node_modules` bytes only |
| `scripts/library-preserve.py` | `LIMEN_LIB_APPLY=1` purged regenerable home caches | preserves data, reports cache candidates only |
| `scripts/cvstos-organ.py` | `--apply` removed chat-app cache children | reports accepted-reaper candidate bytes only |

`scripts/check-removal-acceptance.py` now statically guards these surfaces against
reintroducing direct cleanup tokens.

## Remaining Physical Removal Owners

Physical removal is still implemented only in the dedicated reapers, and only after
their required proof fields pass:

| Surface | Removal class | Gate |
| --- | --- | --- |
| `scripts/reclaim-worktrees.py` | worktree/root reclaim | clean/merged/idle plus `accepted_at`, `archive_proof`, `redaction_proof` |
| `scripts/reap-branches.py` | local branch-ref reap | landed/merged proof plus `accepted_at`, `archive_proof`, `redaction_proof` |
| `scripts/reap-clones.py` | clone-root reap | loss-free clone proof plus acceptance fields |
| `scripts/antigravity-scratch-bridge.py` | Antigravity scratch-root reap | scratch bridge proof plus acceptance fields |

Do not create acceptance JSONL as a shortcut. The JSONL is the human-reviewed
storage/archive/redaction ledger, not a way to quiet a script.

## Remaining Exceptions To Classify Later

These are not general lifecycle cleanup paths, but they still deserve explicit
classification in a future pass:

| Surface | Current reason it remains | Future policy needed |
| --- | --- | --- |
| `cli/src/limen/dispatch.py` Agy bridge | Mirrors an agent-authored file deletion into an isolated PR diff | Distinguish semantic code deletion from storage cleanup in static policy |
| `scripts/claude-fleet-auth-probe.sh` | Removes a temporary Claude config dir that may contain auth material | Secret-temp cleanup policy: redact/no-archive/delete explicitly |
| `scripts/netmode.sh` self-tests | Removes generated self-test temp files | Generated-test-fixture retention or secret-free temp cleanup policy |

## Measurement

Current avtopoiesis measurement remains `29/29` alive with mean score `0.898`
and distance from ideal `10.2%`. The weak axis is still future: more organs can
run and classify without asking, but physical removal now intentionally asks for
accepted proof instead of assuming cleanup is safe.
