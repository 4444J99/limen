# Storage Pulse - 2026-07-06

Read-only storage census run during the deletion-safety hardening pass. No files
were deleted, moved, reaped, archived, or accepted for removal.

## Volume Snapshot

| Mount | Used | Available | Capacity |
| --- | ---: | ---: | ---: |
| `/System/Volumes/Data` | 398Gi | 32Gi | 93% |
| `/Volumes/Archive4T` | 549Gi | 3.0Ti | 16% |

## Local Roots

| Root | Size | Note |
| --- | ---: | --- |
| `~/.gemini` | 26G | Dominated by Antigravity CLI scratch |
| `~/.gemini/antigravity-cli/scratch` | 24G | Largest specific reclaim candidate; bridge required |
| `~/Workspace` | 50G | Repo/product working set |
| `~/Workspace/limen/.worktrees` | 1.7G | PR/side worktrees; largest is PR #665 worktree |
| `~/Workspace/.limen-worktrees` | 2.4G | Shared generated/heal worktrees |
| `~/.claude` | 2.0G | Session/tool state |

Top `~/Workspace` entries:

| Root | Approx size |
| --- | ---: |
| `~/Workspace/limen` | 12.7G |
| `~/Workspace/organvm` | 8.7G |
| `~/Workspace/domus-genoma` | 3.9G |
| `~/Workspace/4444J99` | 3.2G |
| `~/Workspace/a-organvm` | 3.1G |
| `~/Workspace/limen-main-trench-20260628` | 3.1G |
| `~/Workspace/limen-network-substrate-20260628` | 2.8G |

## Antigravity Scratch Bridge Census

Command shape:

```bash
python3 scripts/antigravity-scratch-bridge.py --json
```

Summary:

| Metric | Value |
| --- | ---: |
| Scratch roots | 42 |
| Total bytes | 25,518,538,752 |
| `bridge_required` | 32 |
| `container_review_required` | 3 |
| `preserve_required` | 3 |
| `non_git_review_required` | 3 |
| `keep_active` | 1 |

Top repo buckets:

| Repo | Roots | Approx size |
| --- | ---: | ---: |
| `organvm/session-meta` | 4 | 13.73G |
| `a-organvm/peer-audited--behavioral-blockchain` | 1 | 2.18G |
| `organvm-iii-ergon/sovereign-systems--elevate-align` | 1 | 1.17G |
| `a-organvm/public-record-data-scrapper` | 1 | 1.05G |
| `(no repo)` | 6 | 0.91G |
| `organvm/dot-github--theoria` | 1 | 0.64G |
| `organvm/limen` | 1 | 0.54G |

The largest root, `organvm-session-meta`, is not safe to reap merely because its
remote head is preserved. It has `2741` staged deletions and `2061` untracked
overlap entries, so it is a bridge/classification problem, not a storage cleanup
shortcut.

## Conclusion

The main local reclaim opportunity remains Antigravity scratch, but the bridge
census proves most of it needs owner routing or private preservation before any
accepted reap. Archive4T has enough space for preservation copies; the missing
step is not capacity, it is owner/archive/redaction proof per root.
