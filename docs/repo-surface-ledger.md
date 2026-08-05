# Repo Surface Ledger

Generated: `2026-07-16T16:44:00+00:00`
Repos scanned: `300`

## Scan Roots

- `~/Workspace`

## Harvested Receipts

| Receipt | Status | Evidence |
|---|---|---|
| `docs/repo-surface-ledger.md` | `existing` | generated_at=2026-07-10T01:10:46+00:00, repos_scanned=300 |
| `docs/consolidation/GATES.md` | `current` | generated_at=2026-07-08T01:40:58+00:00, blocking_gates=post-transfer-owner-rewrite-pending, source_repos_outside_organvm=1, transfer_apply_gate_open=True, local_remotes_to_rewrite=10, app_token_wired=True |
| `docs/consolidation/EXECUTION-MANIFEST.md` | `stale-transfer-stage` | status=Staged for execution (all read-only verification complete, scripts ready), gate=Awaiting human `consolidation-gate` open (requires your explicit `--apply` authorization). |
| `docs/current-session-fanout/repo-salvage-consolidation-plan-04.json` | `ready-for-executor-packets` | packet_id=PLAN-04-1c17c8a3, blocked_local_work=5, unconsolidated_plan_hashes=0 |

## Classification Summary

- Unclassified roots: `0`.
- Nested repos: `82`.

### Locations

| Location | Count |
|---|---:|
| `archive` | 0 |
| `nested` | 13 |
| `workspace` | 122 |
| `worktree` | 165 |

### Remote Classes

| Remote class | Count |
|---|---:|
| `github-organvm` | 289 |
| `github-other` | 0 |
| `github-source-owner` | 7 |
| `local-only` | 3 |
| `remote-other` | 1 |

### Dispositions

| Disposition | Count |
|---|---:|
| `blocked-human` | 0 |
| `build` | 4 |
| `consolidate` | 231 |
| `private-sauce` | 3 |
| `publish-stage` | 42 |
| `retire` | 0 |
| `verify` | 20 |

### Gates

| Gate | Count |
|---|---:|
| `none` | 293 |
| `post-transfer-owner-rewrite-pending` | 7 |

## Duplicate Remote Groups

| Remote hash | Repos |
|---|---:|
| `07b5141326fe1486` | 13 |
| `0f05efec3cdc8a72` | 3 |
| `12e871c1ef44d032` | 2 |
| `173dfb112bd036cc` | 4 |
| `1db1d7d788bb64c3` | 4 |
| `25a3228dc037176b` | 2 |
| `26a8234de5ed9c0b` | 3 |
| `2ccc1e3872c85115` | 5 |
| `2cf049847729f153` | 2 |
| `2d479e58d4de5dc4` | 4 |
| `310b9ce49578dd9e` | 3 |
| `34967de00be14dea` | 4 |
| `3d8978088a5b706f` | 2 |
| `4ba17fc4463e951d` | 2 |
| `504c1f787c09aac4` | 6 |
| `5102d88cef70e829` | 2 |
| `53758875e58ae64d` | 76 |
| `53c3121e303b1dde` | 2 |
| `58cae3ae2ad71404` | 11 |
| `60434759f152cbc9` | 2 |
| `66cfe72c11d426df` | 3 |
| `6bd578f7e3df4dc0` | 5 |
| `788150fdb9c0d09f` | 2 |
| `798adafdd0d63567` | 2 |
| `7af321704a67fcb0` | 4 |
| `842ae982a77d357d` | 3 |
| `a64bc49d0d19b82a` | 2 |
| `a829008974b85d0d` | 2 |
| `aa7c79f83dd0ff40` | 3 |
| `b5bc8905138cc474` | 6 |
| `be7d9b3ddc760187` | 2 |
| `c5a6994bab6abb82` | 3 |
| `c6a66ad53b7020b7` | 2 |
| `cb00a17712e577cc` | 2 |
| `d89ad70239309dfe` | 7 |
| `ddcbd60f19d9987a` | 3 |
| `e17cb7a889d5ef3e` | 7 |
| `e6da47c4f17d8ae9` | 2 |
| `e841b09a7964a0a0` | 3 |
| `ea2d84b46d030bc6` | 2 |
| `ed6df59048c8e3f2` | 9 |
| `eef23b9c4944b281` | 2 |

## Repo Surfaces

| Repo | Branch | Dirty | Remote | Products | Tests | Deploys | Visibility | Location | Remote class | Disposition | Gate |
|---|---|---:|---|---:|---:|---:|---|---|---|---|---|
| `~/Workspace/.home-cartridge/Code/organvm/universal-mail--automation` | `main` | 0 | `2ccc1e3872c85115` | 2 | 2 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.home-cartridge/Code/speech-score-engine` | `main` | 0 | `4acc77eee9e44bcd` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/.limen-worktrees/arm-disk-valve` | `chore/arm-disk-capacity-apply` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 0 | `842ae982a77d357d` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/exporter-pr120-fix` | `wt/pr120-fix` | 0 | `173dfb112bd036cc` | 2 | 3 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/gh-4444j99-hokage-chess-39-c15d2ce9` | `limen/gh-4444j99-hokage-chess-39-c15d2ce9` | 1 | `6bd578f7e3df4dc0` | 2 | 3 | 0 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-a-i--skills-27-8f4677cb` | `limen/heal-cifix-organvm-a-i--skills-27-8f4677cb` | 1 | `a829008974b85d0d` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-a-i-council--coliseum-177-7890564d` | `limen/gen-a-organvm-a-i-council--coliseum-ci-green-0620-3e2d` | 4 | `310b9ce49578dd9e` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-a-i-council--coliseum-179-9d294f8a` | `limen/heal-cifix-organvm-a-i-council--coliseum-179-9d294f8a` | 1 | `310b9ce49578dd9e` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-atomic-substrata-4-41b9ec96` | `HEAD` | 0 | `0f05efec3cdc8a72` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-atomic-substrata-4-ccc6d238` | `limen/heal-cifix-organvm-atomic-substrata-4-ccc6d238` | 14 | `0f05efec3cdc8a72` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-bountyscope-13-c8378dbc` | `limen/heal-cifix-organvm-bountyscope-13-c8378dbc` | 1 | `26a8234de5ed9c0b` | 2 | 4 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-bountyscope-16-a4d7e00d` | `pr-16-test` | 1 | `26a8234de5ed9c0b` | 2 | 4 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-community-hub-9-b78c10e5` | `limen/heal-cifix-organvm-community-hub-9-b78c10e5` | 1 | `c5a6994bab6abb82` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-conversation-corpus-engine-42-28f71173` | `limen/heal-cifix-organvm-conversation-corpus-engine-42-28f71173` | 0 | `842ae982a77d357d` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-141-c57c1b89` | `limen/gen-organvm-domus-genoma-security-0627-b9ed` | 1 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-e0f24a23` | `limen/heal-cifix-organvm-domus-genoma-149-e0f24a23` | 1 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-155-f2f394b3` | `limen/jules-gen-organvm-domus-genoma-security-0629-c52d` | 0 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-baceffbf` | `limen/heal-cifix-organvm-domus-genoma-157-baceffbf` | 1 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-e92cc6f4` | `limen/heal-cifix-organvm-domus-genoma-157-e92cc6f4` | 1 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-dot-github--theoria-491-6f539dff` | `limen/heal-cifix-organvm-dot-github--theoria-491-6f539dff` | 0 | `1db1d7d788bb64c3` | 3 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-dot-github--theoria-496-51333a7e` | `limen/heal-cifix-organvm-dot-github--theoria-496-51333a7e` | 0 | `1db1d7d788bb64c3` | 3 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-growth-auditor-13-8e0b3a07` | `limen/heal-cifix-organvm-growth-auditor-13-8e0b3a07` | 1 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-growth-auditor-16-203e2158` | `pr-16` | 0 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-growth-auditor-16-abe0a1a2` | `limen/heal-cifix-organvm-growth-auditor-16-abe0a1a2` | 0 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-growth-auditor-17-05e37ea2` | `limen/heal-cifix-organvm-growth-auditor-17-05e37ea2` | 0 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-growth-auditor-17-8da83fa9` | `limen/heal-cifix-organvm-growth-auditor-17-8da83fa9` | 0 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-412-2d0dda2c` | `limen/heal-cifix-organvm-limen-412-2d0dda2c` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-416-5de40a1c` | `limen/heal-cifix-organvm-limen-416-5de40a1c` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-420-6d674400` | `limen/heal-cifix-organvm-limen-420-6d674400` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-423-40984048` | `limen/heal-cifix-organvm-limen-423-40984048` | 13 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-424-8db5dab0` | `limen/heal-cifix-organvm-limen-424-8db5dab0` | 3 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-426-d7a0e516` | `limen/heal-cifix-organvm-limen-426-d7a0e516` | 1 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-428-4b320e87` | `limen/heal-cifix-organvm-limen-428-4b320e87` | 3 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-429-4471ceb2` | `pr-429` | 1 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-438-980dae49` | `limen/heal-cifix-organvm-limen-438-980dae49` | 2 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-444-a00aa985` | `limen/heal-cifix-organvm-limen-444-a00aa985` | 3 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-447-11a30c5e` | `limen/heal-cifix-organvm-limen-447-11a30c5e` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-451-7e697fef` | `limen/heal-cifix-organvm-limen-451-7e697fef` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-limen-670-dc60ce3a` | `limen/heal-cifix-organvm-limen-670-dc60ce3a` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-100-88b1e47c` | `pr-100` | 2 | `07b5141326fe1486` | 2 | 3 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-104-5198c1b2` | `temp-pr-fix` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-71-5bd74193` | `fix-pr-71-local` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-79-d0960059` | `pr-79` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-83-e010de84` | `limen/heal-cifix-organvm-mirror-mirror-83-e010de84` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-86-05676968` | `pr-86-remote` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-86-45ff622e` | `my-pr-86` | 1 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-90-028f12b1` | `HEAD` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-mirror-mirror-93-f60b2510` | `pr93` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-my--father-mother-19-7988886d` | `limen/heal-cifix-organvm-my--father-mother-19-7988886d` | 0 | `7af321704a67fcb0` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-my--father-mother-21-7bcbbfea` | `limen/heal-cifix-organvm-my--father-mother-21-7bcbbfea` | 1 | `7af321704a67fcb0` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-my--father-mother-21-fd6a0ac5` | `pr-21` | 0 | `7af321704a67fcb0` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-107-3ce185c7` | `limen/heal-cifix-organvm-organvm-engine-107-3ce185c7` | 0 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-109-d6a542c2` | `limen/heal-cifix-organvm-organvm-engine-109-d6a542c2` | 1 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-110-cf645ef4` | `pr-110-branch` | 1 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-136-c3d543d8` | `limen/jules-limen-067-1688` | 3 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-144-0ef4c596` | `limen/heal-cifix-organvm-organvm-engine-144-0ef4c596` | 2 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-engine-144-e2096564` | `limen/heal-cifix-organvm-organvm-engine-144-e2096564` | 1 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-ontologia-11-55899198` | `limen/heal-cifix-organvm-organvm-ontologia-11-55899198` | 1 | `66cfe72c11d426df` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-organvm-ontologia-13-5364f697` | `limen/heal-cifix-organvm-organvm-ontologia-13-5364f697` | 1 | `66cfe72c11d426df` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-peer-audited--behavioral-blockchain-767-dc95acfd` | `limen/heal-cifix-organvm-peer-audited--behavioral-blockchain-767-dc95acfd` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-30-2b47c833` | `limen/heal-cifix-organvm-public-process-30-2b47c833` | 1 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-31-42c38b3d` | `limen/gh-organvm-public-process-13-62ee` | 0 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-31-42c38b3d/_pipeline` | `main` | 0 | `cb00a17712e577cc` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-31-42c38b3d/_standards` | `main` | 0 | `f56297897bd5fbaa` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-33-6d0bb144` | `pr-33` | 2 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-33-6d0bb144/_pipeline` | `main` | 0 | `34967de00be14dea` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-33-6d0bb144/_standards` | `main` | 0 | `aa7c79f83dd0ff40` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-33-f04f03c5` | `limen/gh-organvm-public-process-17-1446` | 1 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-33-f04f03c5/_pipeline` | `main` | 0 | `34967de00be14dea` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-34-61614a22` | `pr-34` | 7 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-34-61614a22/_pipeline` | `main` | 0 | `34967de00be14dea` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-public-process-34-61614a22/_standards` | `main` | 0 | `aa7c79f83dd0ff40` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-scale-threshold-emergence-4-cf350735` | `limen/heal-cifix-organvm-scale-threshold-emergence-4-cf350735` | 1 | `788150fdb9c0d09f` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-schema-definitions-7-535c5b92` | `limen/heal-cifix-organvm-schema-definitions-7-535c5b92` | 1 | `798adafdd0d63567` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-tab-bookmark-manager-28-e70c9bd1` | `pr-28` | 0 | `be7d9b3ddc760187` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-the-invisible-ledger-57-640a827c` | `limen/gen-organvm-the-invisible-ledger-typing-0626-fb12` | 2 | `2d479e58d4de5dc4` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-universal-mail--automation-135-d6b379ca` | `limen/heal-cifix-organvm-universal-mail--automation-135-d6b379ca` | 1 | `2ccc1e3872c85115` | 2 | 2 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-cifix-organvm-writelens-6-022938d8` | `limen/bld-writelens-ci-5acc` | 0 | `25a3228dc037176b` | 1 | 0 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-domus-receipt` | `heal/domus-chronic-receipt` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-4444j99-hokage-chess-136-1cbf3b75` | `limen/heal-rebase-4444j99-hokage-chess-136-1cbf3b75` | 1 | `6bd578f7e3df4dc0` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-4444j99-hokage-chess-139-c0e277d3` | `limen/heal-rebase-4444j99-hokage-chess-139-c0e277d3` | 1 | `6bd578f7e3df4dc0` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-4444j99-hokage-chess-89-77f50ed3` | `limen/heal-rebase-4444j99-hokage-chess-89-77f50ed3` | 1 | `6bd578f7e3df4dc0` | 2 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-a-i-chat--exporter-30-c96e4a23` | `HEAD` | 15 | `173dfb112bd036cc` | 2 | 3 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | `limen/heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | 1 | `173dfb112bd036cc` | 2 | 3 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-domus-genoma-175-fc40bd05` | `limen/heal-rebase-organvm-domus-genoma-175-fc40bd05` | 0 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-dot-github--logos-37-d981b37b` | `limen/gh-organvm-dot-github-logos-18-dad8` | 0 | `60434759f152cbc9` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-mirror-mirror-98-fa9c1d21` | `limen/heal-rebase-organvm-mirror-mirror-98-fa9c1d21` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-496-5891b9ad` | `limen/limen-082-f016` | 1 | `a64bc49d0d19b82a` | 1 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-540caff3` | `limen/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-540caff3` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-721-d20ed684` | `limen/heal-rebase-organvm-peer-audited--behavioral-blockchain-721-d20ed684` | 1 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-729-b6d5e6ef` | `limen/heal-rebase-organvm-peer-audited--behavioral-blockchain-729-b6d5e6ef` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-752-d23f784f` | `limen/heal-rebase-organvm-peer-audited--behavioral-blockchain-752-d23f784f` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-rules-system-bound-10-eba6fc9e` | `pr-10-work` | 0 | `2cf049847729f153` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-session-meta-112-a2258fce` | `limen/heal-rebase-organvm-session-meta-112-a2258fce` | 0 | `53c3121e303b1dde` | 1 | 1 | 0 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-session-meta-142-bb430576` | `limen/heal-rebase-organvm-session-meta-142-bb430576` | 0 | `53c3121e303b1dde` | 1 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/heal-rebase-organvm-universal-mail--automation-134-e483b06c` | `limen/heal-rebase-organvm-universal-mail--automation-134-e483b06c` | 0 | `2ccc1e3872c85115` | 2 | 2 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/lane-fitness-beat-wiring` | `feat/lane-fitness-beat-wiring` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/omega-ask-lineage-live` | `feat/omega-ask-lineage-live` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/org-governance-organ-selffeed-0703-00694775` | `limen/org-governance-organ-selffeed-0703-00694775` | 3 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/peer-audited-726-clean` | `limen/pr-726-cleanup` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/rebind-checkpoint` | `fix/prompt-checkpoint-rebind` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/rev-organvm-mirror-mirror-revenue-ship-0704-134a11b8` | `limen/rev-organvm-mirror-mirror-revenue-ship-0704-134a11b8` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.limen-worktrees/rev-organvm-mirror-mirror-revenue-ship-0704-94c4704f` | `limen/rev-organvm-mirror-mirror-revenue-ship-0704-94c4704f` | 0 | `07b5141326fe1486` | 2 | 3 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/.vox-worktrees/vox2-security-repair-20260710` | `agent/vox-style-observations` | 0 | `ea2d84b46d030bc6` | 2 | 1 | 0 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/domus-genoma` | `codex/artifact-open-package-20260629` | 0 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/edgarflash` | `main` | 5 | `6ef2a267dac80813` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/4444J99/hokage-chess` | `main` | 13 | `6bd578f7e3df4dc0` | 2 | 3 | 0 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/media-ark` | `main` | 6 | `5245d359c6baaba8` | 3 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/4444J99/portfolio` | `main` | 30 | `5102d88cef70e829` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/portvs` | `main` | 0 | `ddcbd60f19d9987a` | 0 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/portvs/.worktrees/triptych-account-excavation-20260706` | `work/triptych-account-excavation-20260706` | 0 | `ddcbd60f19d9987a` | 0 | 0 | 0 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/portvs/.worktrees/triptych-story` | `work/triptych-story` | 0 | `ddcbd60f19d9987a` | 0 | 0 | 0 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/promptscope` | `main` | 4 | `bc304cd55ee9adb8` | 2 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/4444J99/relationship-pipeline` | `main` | 0 | `e841b09a7964a0a0` | 0 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/relationship-pipeline/.worktrees/maddie-boundary-20260629` | `work/maddie-boundary-20260629` | 0 | `e841b09a7964a0a0` | 0 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/relationship-pipeline/.worktrees/student-email-d2l-support-20260629` | `work/student-email-d2l-support-20260629` | 0 | `e841b09a7964a0a0` | 0 | 0 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/4444J99/writelens` | `main` | 6 | `25a3228dc037176b` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/_people-private` | `master` | 0 | `none` | 1 | 0 | 0 | `local-only` | `workspace` | `local-only` | `private-sauce` | `none` |
| `~/Workspace/a-organvm/a-i-chat--exporter` | `master` | 17 | `173dfb112bd036cc` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/card-trade-social` | `main` | 11 | `1dc6954b02523ae0` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/a-organvm/essay-pipeline` | `main` | 1 | `cb00a17712e577cc` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/mirror-mirror` | `limen/gen-organvm-mirror-mirror-ci-green-0702-11e1` | 0 | `07b5141326fe1486` | 2 | 4 | 3 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/my--father-mother` | `main` | 2 | `7af321704a67fcb0` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/narratological-algorithmic-lenses` | `limen/bld-narratological-algorithmic-lenses-harden-20260707` | 0 | `77c140cbdc964703` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/a-organvm/orchestration-start-here` | `main` | 1 | `6dee0a3cf725943d` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/a-organvm/organvm-engine` | `main` | 0 | `d89ad70239309dfe` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/peer-audited--behavioral-blockchain` | `limen/rev-styx-metered-billing-57ec` | 0 | `e17cb7a889d5ef3e` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/public-record-data-scrapper` | `main` | 8 | `12e871c1ef44d032` | 2 | 3 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/stakeholder-portal` | `discover-organvm-stakeholder-portal` | 0 | `19cafb7143781e3f` | 2 | 4 | 2 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/a-organvm/tab-bookmark-manager` | `main` | 3 | `be7d9b3ddc760187` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/the-invisible-ledger` | `main` | 10 | `2d479e58d4de5dc4` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/a-organvm/universal-mail--automation` | `pr-53` | 0 | `2ccc1e3872c85115` | 1 | 2 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/advocata` | `main` | 0 | `143dce056d5e8257` | 2 | 2 | 0 | `remote-present` | `workspace` | `github-organvm` | `build` | `none` |
| `~/Workspace/domus` | `main` | 0 | `a224b0268b1c0637` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/domus-uma-mail-wrapper-154` | `codex/uma-mail-wrapper-154` | 0 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/edu-organism-student-email-doctrine-20260709` | `codex/student-email-doctrine-20260709` | 0 | `c00cfe015475eca0` | 0 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/gamified-coach-interface` | `main` | 0 | `939782610a20d2f1` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/limen` | `main` | 1 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/agent-aefc63d95daa3131b` | `corpus-verify` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/arca-chunked-vault` | `worktree-arca-chunked-vault` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/bifrons-autopoiesis` | `worktree-bifrons-autopoiesis` | 1 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/bright-cooking-kahn` | `HEAD` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/config-ownership-limen` | `worktree-config-ownership-limen` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/docs-estate-audit-outcomes` | `docs/estate-audit-outcomes` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/endless-watcher-fix` | `fix/governor-pause-release` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+backblaze-exclusion-estate` | `feat/backblaze-exclusion-estate` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+mail-tiers-registry` | `heal/worktree-orphan-sweep` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+observatory-scaffold` | `feat/observatory-complete` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+opencode-tier-ladder` | `heal/revert-opencode-lane-truth-932` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+pytest-scope-guard` | `feat/pytest-scope-guard` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+vitals-load-axis` | `feat/vitals-load-axis` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat+workstream-channels` | `heal/revive-self-heal-beat` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-agent-docs-discipline-parity` | `feat/agent-docs-discipline-parity` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-codex-gemini-tier-derivation` | `feat/codex-gemini-tier-derivation` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-gcp-sa-organ` | `heal/derive-mediark-host-cloudflare` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-identity-organ` | `fix/sync-hishand-dup-issues` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-insight-gap-classification` | `feat/insight-gap-classification` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/feat-relationship-review-sensor` | `worktree-feat-relationship-review-sensor` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/fix-aw-capability-predicates` | `fix/aw-capability-predicates` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/fix-overnight-zero-launch` | `fix/overnight-zero-launch` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/fix-owner-contract-selfheal` | `fix/overnight-owner-contract-selfheal` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/fluttering-twirling-abelson` | `feat/funnel-l2-lane` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/heal-pr-fixes-0715` | `fix/agy-steps-schema-adapter` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/heal-pr-verdicts-lever` | `docs/heal-pr-verdicts-lever` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/horrevm-custody` | `feat/horrevm-custody` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/horrevm-storage-roles` | `feat/horrevm-storage-roles` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/insights-suggestion-ledger` | `feat/insights-suggestion-ledger` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/linear-conjuring-bear` | `session/post-moneta-durability` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/needs-human-truth` | `fix/needs-human-truth` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/retro-2026-07-08` | `worktree-retro-2026-07-08` | 6 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/sovereign-inference-plan` | `feat/local-floor-routing` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/ticklish-bubbling-robin` | `feat/phase-2-doctrine-surfaces` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/verify-ci-hardening` | `fix/prgate-scoped` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/vltima-closeout-20260709` | `codex/vltima-closeout-20260709` | 10 | `a489a4d5e79c04e9` | 1 | 1 | 3 | `remote-present` | `worktree` | `remote-other` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_29a15be5-9f8-2` | `worktree-wf_29a15be5-9f8-2` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_4231e62a-8b1-2` | `feat/exporter-first-dollar-wire` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_4231e62a-8b1-3` | `feat/disk-capacity-sensor` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_6c57f239-cfd-3` | `heal/aw-tabvlarivs-846-rebase` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_6c57f239-cfd-5` | `heal/censor-direct-push-close` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/wf_6c57f239-cfd-6` | `feat/worktree-debt-trend` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.claude/worktrees/whole-estate-insights` | `docs/whole-estate-insights` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.codex/worktrees/claude-no-modal-dispatch-0714` | `agent/claude-no-modal-dispatch` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.codex/worktrees/epoch-closeout-20260714` | `codex/epoch-closeout-20260714` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.codex/worktrees/modular-continuation-20260714` | `codex/agy-discovery-overflow-20260715` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/agent-checkout-guard-20260709` | `codex/agent-checkout-guard-20260709` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/dispatch-admission-closeout-20260709` | `closeout/dispatch-admission-20260709` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/mail-story-mining-20260706` | `feat/mail-story-mining-20260706` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/next-autonomous-epoch-20260714` | `work/next-autonomous-epoch-20260714` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/resource-safe-closeout-20260709` | `codex/resource-safe-closeout` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/safe-storage-reclaim-20260709` | `codex/safe-storage-reclaim-20260709` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/session-scope-boundary-closeout` | `codex/session-scope-boundary-closeout` | 2 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/the-invisible-ledger` | `work/invisible-ledger-trial-followups-20260629` | 0 | `2d479e58d4de5dc4` | 2 | 4 | 2 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/universal-kernel-recordkeeper-20260705` | `feat/universal-kernel-recordkeeper-20260705` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/.worktrees/warp-agent-routing-20260629` | `work/warp-agent-routing-20260629` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen/domus-genoma` | `limen/gh-organvm-domus-genoma-278-e703f515` | 0 | `ed6df59048c8e3f2` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen-student-email-closeout-20260709` | `codex/student-email-doctrine-cleanup-20260709` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/limen-watch-pause-guard-0714` | `agent/overnight-watch-pause-guard` | 0 | `53758875e58ae64d` | 1 | 1 | 3 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato` | `main` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/overnight-audio-soundtest` | `exp/overnight-audio-soundtest` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/overnight-fighter-combat-feel` | `exp/overnight-fighter-combat-feel` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/overnight-integration-qa` | `exp/overnight-integration-qa` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/overnight-visual-coherence` | `exp/overnight-visual-coherence` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-game-current` | `exp/rob-game-current` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-game-nano-world` | `exp/rob-game-nano-world` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-game-polish-release` | `exp/rob-game-polish-release` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-game-touch-combat` | `exp/rob-game-touch-combat` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-roadmap-implementation` | `exp/rob-roadmap-implementation` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/micro-tato/.lanes/rob-transcript-completion` | `exp/rob-transcript-completion` | 0 | `58cae3ae2ad71404` | 1 | 0 | 1 | `remote-present` | `nested` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/.worktrees/in-my-head-vox5-lifecycle-final` | `agent/vox5-dynamic-movie-scene` | 0 | `eef23b9c4944b281` | 2 | 1 | 0 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/4-ivi374-F0Rivi4` | `feat-initial-swarm-scaffold` | 0 | `70ac0639dd5fdd07` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/4444J99` | `main` | 0 | `6d74f9baa789b001` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/4444J99.github.io` | `main` | 2 | `b3e5c984da7b9d16` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/_agent` | `main` | 0 | `dab03b6c4179cbe5` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/_agent-health` | `main` | 0 | `548e777a6937bf0f` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/a-i--skills` | `main` | 0 | `a829008974b85d0d` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/a-i-council--coliseum` | `main` | 0 | `310b9ce49578dd9e` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/a-mavs-olevm` | `master` | 3 | `c6a66ad53b7020b7` | 2 | 2 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/a-recursive-root` | `main` | 0 | `0d9b0bf7e8c8df27` | 2 | 2 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/alchemia-ingestvm` | `main` | 0 | `d1e7c618f5391901` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/alchemical-synthesizer` | `main` | 0 | `de0e545df88c8ca7` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/analytics-engine` | `main` | 0 | `a109c790968ed5d5` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/atomic-substrata` | `limen/heal-cifix-organvm-atomic-substrata-3-1445` | 0 | `0f05efec3cdc8a72` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/bountyscope` | `pr-16` | 0 | `26a8234de5ed9c0b` | 2 | 4 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/brainstorm-20260423` | `main` | 22 | `09cfb8d5e53e25f4` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/call-function--ontological` | `main` | 0 | `0b18f313b7001304` | 2 | 2 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/case-studies-methodology` | `main` | 0 | `19860a03598813de` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/chthon-oneiros` | `main` | 0 | `535186f0be77b82e` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/claude-runtime-state` | `main` | 0 | `22ba023c99c97222` | 0 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/community-hub` | `main` | 0 | `c5a6994bab6abb82` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/content-engine--asset-amplifier--a-organvm-legacy` | `feature/stripe-checkout` | 0 | `0d16d8d25923cf38` | 2 | 4 | 0 | `remote-present` | `workspace` | `github-organvm` | `build` | `none` |
| `~/Workspace/organvm/digital-income-organism-inquiry` | `main` | 1 | `ba0aa690084543c4` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/distribution-strategy` | `main` | 0 | `c181dfd3d26e49d6` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/dot-github--logos` | `limen/promote-pages-theoria-copy-logos` | 0 | `60434759f152cbc9` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/dot-github--poiesis` | `main` | 0 | `afbf878d46e51ded` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/dot-github--taxis` | `main` | 0 | `ad560eaa4818c238` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/dot-github--theoria` | `limen/resolve-organvm-i-theoria-.github-459-1bb0` | 1 | `1db1d7d788bb64c3` | 3 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/dot-github--theoria/.claude/worktrees/agent-a9ca0d473436e9943` | `worktree-agent-a9ca0d473436e9943` | 21 | `1db1d7d788bb64c3` | 3 | 3 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/enterprise-plugin` | `master` | 0 | `26ac73f3cbeaa173` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/etceter4-revival` | `etceter4-revival` | 0 | `c6a66ad53b7020b7` | 2 | 2 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/fetch-familiar-friends` | `main` | 0 | `3cbf0e9360ac5590` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/hospes` | `main` | 0 | `a4bf0873605a3267` | 2 | 2 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/in-my-head` | `master` | 0 | `eef23b9c4944b281` | 2 | 2 | 0 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/ivi374ivi027-05` | `main` | 0 | `e3d2b7cf67c4fbe4` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/kerygma-profiles` | `main` | 0 | `8f16df9dceb1f925` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/life-betterment-simulation` | `main` | 0 | `7cbe15849ca7860d` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/linguistic-atomization-framework` | `main` | 0 | `de011e19c2e6cb95` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/manumissio` | `main` | 0 | `7e09870a663ed746` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/meta-source--ledger-output` | `main` | 0 | `bbabe06147fd09c6` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/metasystem-master` | `master` | 0 | `9bfc179a32c37a7a` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/my-knowledge-base` | `master` | 0 | `4f6dc19c34cc602e` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/nexus--babel-alexandria` | `main` | 0 | `3c65f20d924effa4` | 2 | 2 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/org-dotgithub` | `main` | 3 | `4ec57ee3188d2f3f` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/organon-noumenon--ontogenetic-morphe` | `main` | 40 | `70df97765fad3984` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/organvm-ontologia` | `main` | 0 | `66cfe72c11d426df` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/pages--theoria-copy--kerygma` | `main` | 0 | `44056957bb91147e` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/payrail` | `main` | 0 | `4938273bf11483d6` | 2 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/petasum-super-petasum` | `main` | 0 | `fe535f0cf3122457` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/portfolio` | `main` | 4 | `5102d88cef70e829` | 2 | 4 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/public-process` | `pr-28` | 0 | `b5bc8905138cc474` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/public-process/_pipeline` | `main` | 0 | `34967de00be14dea` | 2 | 1 | 1 | `remote-present` | `nested` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/organvm/public-process/_standards` | `main` | 0 | `aa7c79f83dd0ff40` | 1 | 0 | 1 | `remote-present` | `nested` | `github-source-owner` | `consolidate` | `post-transfer-owner-rewrite-pending` |
| `~/Workspace/organvm/public-record-data-scrapper` | `security-hardening-0630` | 0 | `12e871c1ef44d032` | 2 | 3 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/radix-recursiva-solve-coagula-redi` | `main` | 0 | `a148b623ffe1ce75` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/recursive-engine--generative-entity` | `main` | 3 | `2cd3e5e4ecac331b` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/render-second-amendment` | `unknown` | 0 | `06392b1ff9699027` | 0 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/schema-definitions` | `main` | 0 | `798adafdd0d63567` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/shared-remembrance-gateway` | `main` | 0 | `f00295490ed8ec51` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/sign-signal--voice-synth` | `main` | 0 | `37269d4dd7d02729` | 2 | 2 | 0 | `remote-present` | `workspace` | `github-organvm` | `build` | `none` |
| `~/Workspace/organvm/styx-behavioral-art` | `main` | 0 | `93b6498ebd18b0fc` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/system-governance-framework` | `main` | 0 | `3e6baf0c2c1a47f7` | 3 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/the-actual-news` | `main` | 0 | `9e0c72b6032d37e0` | 2 | 5 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/the-invisible-ledger` | `pr-41` | 0 | `2d479e58d4de5dc4` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/trendpulse` | `main` | 0 | `e435caaf27abdb05` | 2 | 4 | 2 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/universal-mail--automation` | `main` | 6 | `2ccc1e3872c85115` | 2 | 2 | 2 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/universal-node-network` | `pr-9` | 0 | `c631051b0d8b8e54` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/vigiles-aeternae--agon-cosmogonicum` | `main` | 0 | `a76be84a7b9175f9` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/vigiles-aeternae--theatrum-mundi` | `main` | 2 | `b9c61a3f6a74af91` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/visual-substrate-inquiry` | `unknown` | 0 | `0b207c623329bedf` | 0 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm/vox` | `master` | 1 | `ea2d84b46d030bc6` | 2 | 1 | 0 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm/vox--publica` | `main` | 0 | `10de4abe8728d536` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/vulnpulse` | `main` | 0 | `e684d0fa84a76e41` | 2 | 4 | 2 | `remote-present` | `workspace` | `github-organvm` | `publish-stage` | `none` |
| `~/Workspace/organvm/your-fit-tailored` | `main` | 2 | `7a48c6977bec4228` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm-community-hub` | `pr-9` | 0 | `c5a6994bab6abb82` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-corpvs-testamentvm` | `main` | 0 | `a64bc49d0d19b82a` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/.github` | `main` | 0 | `3d8978088a5b706f` | 3 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/conversation-corpus-engine` | `main` | 0 | `842ae982a77d357d` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/growth-auditor` | `pr-12` | 0 | `504c1f787c09aac4` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/mesh` | `discover-organvm-mesh-1782154528` | 0 | `82645b2f16140b3c` | 2 | 1 | 0 | `remote-present` | `workspace` | `github-organvm` | `build` | `none` |
| `~/Workspace/organvm-i-theoria/rules-system-bound` | `limen/recover-gh-organvm-i-theoria-rules-system-bound-1` | 0 | `2cf049847729f153` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/scale-threshold-emergence` | `discover-value` | 0 | `788150fdb9c0d09f` | 2 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/sovereign--ground` | `main` | 0 | `51d0929017aca123` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm-i-theoria/studium-generale` | `main` | 1 | `4ba17fc4463e951d` | 1 | 1 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-i-theoria/studium-generale/.claude/worktrees/provost-grading-engine` | `feat/provost-grading-engine` | 0 | `4ba17fc4463e951d` | 2 | 1 | 1 | `remote-present` | `worktree` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-iii-ergon/organvm-iii-ergon.github.io` | `main` | 0 | `e5c0500a3ae3d1ee` | 1 | 0 | 0 | `remote-present` | `workspace` | `github-organvm` | `verify` | `none` |
| `~/Workspace/organvm-iii-ergon/specvla-ergon--avditor-mvndi` | `main` | 4 | `e6da47c4f17d8ae9` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/organvm-v-logos/.github` | `main` | 5 | `3d8978088a5b706f` | 1 | 0 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/script-doctor` | `master` | 0 | `none` | 1 | 0 | 1 | `local-only` | `workspace` | `local-only` | `private-sauce` | `none` |
| `~/Workspace/specvla-ergon--avditor-mvndi` | `discover-value-thesis` | 0 | `e6da47c4f17d8ae9` | 2 | 3 | 1 | `remote-present` | `workspace` | `github-organvm` | `consolidate` | `none` |
| `~/Workspace/studio` | `feat/launch-ready` | 0 | `none` | 1 | 0 | 0 | `local-only` | `workspace` | `local-only` | `private-sauce` | `none` |

## Contract

- Public receipts use hashes for remotes and product surfaces.
- Exact local paths, remote URLs, and product names stay in the ignored private index.
- Every discovered root carries a location class, remote class, disposition, and gate field.
- Discovery roots are derived from `LIMEN_REPO_ROOTS`, `LIMEN_WORKSPACE_ROOT`, `LIMEN_WORKTREE_ROOT`, or the current Limen root.
