# Issue draft disposition — 2026-09-26

## Closeout blocker

The live-root gate remains blocked. This duplicate draft was not filed: [#2752](https://github.com/4444J99/limen/issues/2752) owns capsule residue, [#1346](https://github.com/4444J99/limen/issues/1346) owns the shared live root, and [#685](https://github.com/4444J99/limen/issues/685) owns storage and worktree lifecycle. Fresh observations were posted to those issues.

## Verified local evidence

- `python3 scripts/live-root-gate.py` reported blocked with 3 blockers; a separate earlier write produced `docs/live-root-gate.md`.
- The live root is detached at `d4ec45cb456fa63a5c594eb429537fac572ce320`, dirty, and 54 commits behind the gate's release head `91cc8b3dd4f6c6b6cc53da3dc8bd7dee8b88c568`.
- Dirty paths: `docs/branch-hygiene.md`, `docs/jules-orphan-adoptions.jsonl`, and generated `docs/live-root-gate.md`.
- Heartbeat plist exists, but launchd reports it is not running.
- `scripts/reclaim-worktrees.py --check --json` found four candidates; no reclaim was applied.
- `scripts/residue-census.py --json` reported one measured breach (worktrees 23 against cap 8) and two unmeasured storage rows. Remote branch count is over its report-only cap.
- Canonical successor capsule: `work/spine-closeout-successor-20260926-v2`, carried by open [PR #2759](https://github.com/4444J99/limen/pull/2759). The invalid root capsule [PR #2756](https://github.com/4444J99/limen/pull/2756) was closed unmerged.
- GitHub API access was available from the admitted operator worktree. From the clean pushed successor worktree, `bash scripts/no-tasks-on-me.sh` and `python3 scripts/credential-wall.py --check` both exited 0.

## Required owner actions

1. Follow #1346 to preserve the two live-root edits and daemon-owned queue before release convergence.
2. Follow #685 for the worktree cap breach and two unmeasured storage rows. The candidate census is not deletion authority.
3. Follow #2752 for local capsule residue and the final closeout predicate.
4. Re-derive GitHub state through `gh api` at the next boundary.

## Completion predicate

No new issue should be opened from this draft. Close the existing owner issues only when their own predicates and receipts pass.

## Safety boundary

Do not reset, switch, stash, delete worktrees/branches, reload launchd, merge, deploy, or close other human-owned issues/PRs without their separate owner authority.
