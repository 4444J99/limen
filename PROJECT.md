# Project: Ecosystem PR Remediation, Rebase, CI Repair, and Merge Operation

## Current execution authority — workspace recovery

The chamber campaign below is a preserved historical plan, not current dispatch authority.
Its unfinished milestones remain unfinished. The user's 2026-09-16 recovery decision permits
one recovery writer; ordinary autonomous implementation and resource growth stay contained.
After recovery, only priorities explicitly enabled in the existing autonomy policy may launch.
A pause expiry, merged recovery PR, historical handoff, or previously listed milestone cannot
authorize a new chamber campaign. Use the [finite recovery contract](docs/architecture/finite-workspace-recovery.md)
and [current receipts](docs/receipts/workspace-recovery-20260916.md).

The historical counts and milestone labels below are preserved evidence, not live completion
or ownership claims. Do not make all projects or repositories green a recovery prerequisite.

## Architecture & Operational Topology
The Ecosystem PR Remediation operation spans all active repositories across `/Users/4jp/Workspace` and ecosystem remotes.
Operations are strictly partitioned into isolated Chamber execution environments using temporary git worktrees (`/Users/4jp/Workspace/chamber_worktrees/<chamber>/<repo>/pr-<pr_num>`) to prevent interference with main workspaces and live daemons.

### Protected Boundary Isolation
- `limen-private-document-review-20260825` (`task/private-document-review-20260825`): Read/write/rebase strictly forbidden.
- `limen` (`feat/conduct-role-hardening-and-permissions`): Branch strictly untouched.
- `4444J99/universal-mail--automation/`: Strictly untouched.
- Active Codex and OpenCode runtime daemons (41 background processes): Preserved without disruption.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Ecosystem Census & Invariant Discovery | Survey all 249 ecosystem repos, catalog 780 PRs (181 local), audit invariants | M0 (Done) | survey |
| 2 | E2E Testing & Verification Harness | Requirement-driven opaque-box test harness validating R1-R5 criteria | M1 (E2E Track) | ORIGINAL_REQUEST |
| 3 | Chamber 1 Remediation (Organvm Core) | Rebase, CI/test repair, merge, and reap for `limen`, `organvm-engine`, `domus-genoma`, `corpvs` | M2 | survey |
| 4 | Chamber 2 Remediation (Ergon & Platforms) | Rebase, CI/test repair, merge, and reap for `collaboration-ops`, `speech-score`, `trendpulse`, `mirror-mirror`, `your-fit-tailored` | M3 | survey |
| 5 | Chamber 3 Remediation (Taxis & 4444J99) | Rebase, CI/test repair, merge, and reap for `sovereign-systems`, `victoroff-os`, `blockchain`, `a-i--skills` | M4 | survey |
| 6 | Chamber 4 Remediation (Pipelines & Ring) | Rebase, CI/test repair, merge, and reap for `portfolio`, `essay-pipeline`, `relationship-pipeline`, `application-pipeline`, `social-automation`, `portvs`, `styx-*` | M5 | survey |
| 7 | Final Ecosystem E2E Verification & Reaping Audit | 100% E2E test verification, remote branch deletion, temporary worktree reaping, 0 unceremonious closures | M6 | ORIGINAL_REQUEST |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Survey & Census | Exhaustive cataloging of all 780 PRs, diffs, CI causes, and protected invariants | none | DONE |
| M1 | E2E Testing Track | Requirement-driven test suite validating R1-R5, publishes `TEST_READY.md` | M0 | IN_PROGRESS |
| M2 | Chamber 1: Organvm Core | Rebase, CI repair, local test verification, and merge for Core repos | M0 | IN_PROGRESS |
| M3 | Chamber 2: Ergon & Platforms | Rebase, CI repair, local test verification, and merge for Ergon repos | M0 | IN_PROGRESS |
| M4 | Chamber 3: Taxis & Sovereign | Rebase, CI repair, local test verification, and merge for Taxis & 4444J99 repos | M0 | IN_PROGRESS |
| M5 | Chamber 4: Pipelines & Ring | Rebase, CI repair, local test verification, and merge for Pipelines & Outer Ring | M0 | IN_PROGRESS |
| M6 | Final Verification & Reaping | Run full E2E test suite (100% pass), reap all temporary worktrees, verify zero unceremonious closures | M1, M2, M3, M4, M5 | PLANNED |

## Interface Contracts & Remediation Protocols

### Worktree Protocol
- Creation must use the existing admitted worktree initializer or session helper with a
  keeper-owned approved work key. Reserve both branch and checkout allowances before creation.
  Use configured runtime roots; historical chamber paths do not authorize fresh scratch.
- Upstream fetch and rebase require the current task's ownership and exact-base contract.
- Conflict resolution: 3-way merge preserving upstream improvements and PR features.
- Verification is scoped, with at most ten minutes inside the thirty-minute attempt; reuse
  unchanged bound receipts. One changed-input correction is permitted within the existing
  outcome's 120 cumulative agent-minutes. Exhaustion checkpoints and stops continuation.
- Push and merge use the repository's current exact-head policy. Branch deletion uses GitVS
  dispositions and the existing exact-tip reaper; preservation never implies merger.
- Release records a checkout disposition. Retire only clean, inactive, durably recoverable
  copies through the journaled non-forced lifecycle. Preserve dirty and ignored payloads,
  advanced heads, human sessions, and uncertain custody. Resume interrupted cleanup idempotently.

### Diagnostic Retention Protocol (R4)
- Zero unceremonious closures.
- If a PR is blocked by architectural design requiring human steering, post a structured diagnostic comment retaining full findings and keep open.
- If a PR is superseded by a newer PR, reference the superseding PR in a comment and confirm before cleanup.

## Code Layout
- Agent metadata: `/Users/4jp/Workspace/limen/.agents/<type>_<name>/`
- Chamber worktrees: `/Users/4jp/Workspace/chamber_worktrees/<chamber_name>/<repo_name>/`
- Target repositories: `/Users/4jp/Workspace/*`
