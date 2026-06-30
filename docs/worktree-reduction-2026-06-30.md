# Worktree Reduction Receipt - 2026-06-30

Generated: `2026-06-30T16:51:39Z`

This receipt records the direct-session reduction pass requested before photos sorting and
creative-lane work. It does not claim unrelated queue tasks and does not mutate `tasks.yaml`.

## Preconditions

- `git push origin main` advanced `organvm/limen` `main` to `9f8be9834f75eba24572f4804a672faf89eb2b55`.
- `tasks.yaml` already had async-reservation edits before this pass and was intentionally left
  unstaged.
- `studium/ledger/studium-2026-06-30.md` was intentionally left separate and unstaged.
- `python3 scripts/validate-task-board.py` reported `Task board statuses valid (1533 tasks)`.
- `python3 scripts/verify-dispatch.py --quiet` exited 0.

## Removed Roots

The following roots are safe to remove in this pass because they are remote-merged,
remote-superseded, or documented disposable residue:

| Root | Class | Receipt |
|---|---|---|
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | remote-merged / patch-equivalent | PR `organvm/public-record-data-scrapper#328` is `MERGED`, head `3af406915ec3a3c67f0843f963cb6a3658bcc9d9` matches the local worktree, and `git cherry origin/main HEAD` reports the local commit as patch-equivalent. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | remote-superseded | `docs/worktree-preservation-receipts.json` records `superseded_on_origin_main`; current `origin/main` includes broader loader, CLI, and smoke-test coverage. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | documented generated-results residue | `docs/worktree-preservation-receipts.json` records private patch SHA-256 `92dc514490c7bbf3c6a14eb3889656563d070a23af55af3d64f2a16999d63bc9`; current local deltas are only the 11 `structure-tests/results/*.json` snapshots. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | documented non-source residue | Empty `dist/` directory only; recorded as `empty_generated_residue`. |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | documented non-source residue | `.vite/deps` cache metadata only; recorded as `cache_only_residue`. |
| `gen-organvm-limen-ci-green-0622-9c4d` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `gen-organvm-limen-security-0622-88e5` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `org-consulting-organ-face-0630-0073` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `org-education-organ-face-0630-58c0` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `org-governance-organ-deepen-0630-acad` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `org-media-organ-deepen-0630-43a4` | disposable non-git log shell | Contains only `logs/session-lifecycle-pressure.md` and `logs/session-lifecycle-pressure.json`. |
| `triptych-media-offload-20260629` | collapsed Portvs worktree | Pushed `work/triptych-media-offload-20260629` to `b7a5fc2`, fast-forwarded and pushed `work/triptych-story` to the same commit, then removed the redundant local checkout. |

## Kept Roots

- Active `<6h` and `<24h` daemon/repair/photo roots were kept for harvest.
- Portvs `triptych-story` was kept as the active creative surface after absorbing
  `triptych-media-offload-20260629`.
- `photos-universe-20260629-182431` was kept as the active photos lane.
- Owner-blocker, open-PR, not-merged, and unpushed roots outside the explicit removals were kept.

## Post-Reduction Gates

Run after removal:

- `python3 scripts/worktree-debt.py --json`
- `python3 scripts/validate-task-board.py`
- `python3 scripts/verify-dispatch.py --quiet`

Observed after-state:

- Worktree debt: `7` debt-bearing roots / `35` total roots, cap `12`.
- `/Users/4jp/Workspace/.limen-worktrees`: `1.1G`.
- Remaining debt classes: `not-merged-to-default=7`.
- Active roots created or updated by the live fleet during this pass were kept for harvest.
