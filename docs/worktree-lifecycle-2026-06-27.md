# Worktree Lifecycle Inventory - 2026-06-27

This inventory records the kept-safe roots under `/Users/4jp/Workspace/.limen-worktrees`.
No directory was deleted or removed during this pass.

The live reconciliation surface is
[`docs/worktree-lifecycle-ledger.md`](worktree-lifecycle-ledger.md). This dated file is the
snapshot from the first audit; use the ledger for current disposition, origin-receipt gaps, and
drain order.

Post-audit update: the background reaper later reclaimed the two content-preserved roots
`gen-organvm-mirror-mirror-security-0622-c552` and
`gen-organvm-the-invisible-ledger-security-0622-d8f8` at `2026-06-27T13:05:49Z`.
Both had already been classified as patch-equivalent to default, so no unique source was lost.
Policy update 2026-06-29: future automated drain runs apply safe reclaims by default
(`LIMEN_RECLAIM_APPLY=1`). Set `LIMEN_RECLAIM_APPLY=0` for preview-only operation.

Post-audit update: `bld-universal-mail--automation-readme-9031` was rebased to
current `origin/main`, committed as `29f6b4b`, pushed, and preserved as draft PR
[#108](https://github.com/organvm/universal-mail--automation/pull/108). It is no
longer dirty local-only work, though it remains lifecycle debt until merged or
explicitly superseded.

Post-audit update: `bld-media-ark-tests-2698` was rebased to current
`origin/main`, the useful dirty test draft was ported into the current test
module, platform test-contract gaps were fixed, and the result was preserved as
draft PR [#50](https://github.com/organvm/media-ark/pull/50) at `b7509dc`.

Post-audit update: `bld-mirror-mirror-harden-350f` was rebased to current
`origin/main`, the stale draft PR branch was replaced with an explicit
force-with-lease from `3d822c6` to `f44da8e`, and the resolved webhook
hardening was preserved as draft PR
[#67](https://github.com/organvm/mirror-mirror/pull/67). The PR is clean and
GitHub CI passed; the local root is no longer dirty local-only work, though it
remains lifecycle debt until merged or explicitly superseded.

Reclaim policy after this audit: a root is reapable only when it is clean, idle, and its
content is preserved on the remote default branch. Preservation can be exact SHA reachability
or `git cherry <default> HEAD` patch equivalence after squash/rebase. Dirty work,
unique-unpushed commits, open/unmerged branches, active roots, and non-Git residue stay visible.

## Summary

- 21 roots inspected.
- 0 roots reclaimed.
- 12 dirty roots: local file changes need review, commit, PR, or explicit discard-after-preserve.
- 4 unique-unpushed roots: local commits need push/PR or absorption into an existing branch.
- 2 non-Git roots: filesystem residue needs classification before any cleanup.
- 1 active root: recently touched after rebase/classification; re-check after the idle grace window.
- 2 content-preserved roots: dry-run says they are reapable, but no directory was removed in this pass.

## Kept Roots

| Root | Repo | Branch / Head | Reason Kept | Next Lifecycle Action |
|---|---|---|---|---|
| `bld-domus-genoma-ci-23a9` | `organvm/domus-genoma` | `limen/bld-domus-genoma-ci-23a9` / `c22646f` | dirty: `.github/workflows/ci.yml` | Review CI workflow, commit if valid, open/update PR. |
| `bld-media-ark-tests-2698` | `organvm/media-ark` | `limen/bld-media-ark-tests-2698` / `b7509dc` | preserved as draft PR #50 | Review and merge, or name a successor that preserves the capture/platform test coverage. |
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror` | `limen/bld-mirror-mirror-harden-350f` / `f44da8e` | preserved as draft PR #67 | Review and merge, or name a successor that preserves the Stripe webhook hardening. |
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | `limen/bld-my--father-mother-harden-44b2` / `18730a2` | dirty: `main.py` | Review hardening diff, run tests, commit and PR. |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | `limen/bld-promptscope-next-rev-3fde` / `4fa725b` | dirty: `public/app.js`, `public/index.html`, `src/index.ts` | Review product diff, run build/tests, commit and PR. |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation` | `limen/bld-universal-mail--automation-readme-9031` / `29f6b4b` | preserved as draft PR #108 | Review and merge, or name a successor that preserves the README modernization. |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter` | `limen/bld2-a-i-chat--exporter-integration-tests-a00b` / `d0d633c` | unpushed: 2 commits | Push branch, open/update PR, or absorb into successor PR. |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine` | `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e` / `be4b920` | dirty: `pyproject.toml` | Review CI fix, run tests, commit and PR. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | `limen/cifix-organvm-i-theoria-hierarchia-mundi-3145` / `677df2b` | dirty: package files and `tests/` | Review CI/test diff, run suite, commit and PR. |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles` | `limen/discover-organvm-kerygma-profiles-6c74` / `a8a029f` | dirty: generated `egg-info` and `__pycache__` | Confirm generated-only dirt, then clean via project-safe ignore/cleanup. |
| `exporter-mp` | `organvm/a-i-chat--exporter` | `limen/exporter-multiprovider` / `6c88427` | unpushed: 2 commits, no upstream | Push branch and open PR for multiprovider work. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | `limen/gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` / `80e7617` | dirty: generated structure-test results | Classify generated result drift, commit only if intended. |
| `gen-organvm-mirror-mirror-security-0622-c552` | `organvm/mirror-mirror` | `limen/gen-organvm-mirror-mirror-security-0622-c552` / `afed90a` | content-preserved: patch-equivalent to default | Reapable by `reclaim-worktrees.py --apply` after operator acceptance; no unique code remains in this root. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | unknown | n/a | not a Git worktree; empty sample | Classify residue before cleanup. |
| `gen-organvm-the-invisible-ledger-security-0622-d8f8` | `organvm/the-invisible-ledger` | `limen/sec-audit-0622` / `b208078` | content-preserved: patch-equivalent to merged PR #30 | Reapable by `reclaim-worktrees.py --apply` after operator acceptance; no unique code remains in this root. |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | `limen/gen-organvm-universal-mail--automation-test-coverage-0625-151e` / `bff9ae1` | dirty: broad deletion set | High-risk review before any action; preserve until root cause is known. |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons` | `limen/gh-organvm-object-lessons-19-605a` / `cf89af6` | unpushed: 2 commits | Push branch and open/update PR for Letterboxd ingestion work. |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `organvm/the-invisible-ledger` | `limen/resolve-a-organvm-the-invisible-ledger-4-f657` / `2e785e4`; preserved tip `preserve/resolve-a-organvm-the-invisible-ledger-4-f657-1741370` | active: rebased to current `origin/main`; old PostgreSQL adapter patch superseded by landed upstream work | Re-check after idle grace; do not open a duplicate PR unless audit finds missing value beyond the landed adapter/billing work. |
| `resolve-organvm-i-theoria-.github-459-1ade` | `organvm/.github` | `limen/resolve-organvm-i-theoria-.github-459-1ade` / `efff71c` | dirty: workflows, dashboard types, `tsconfig.json` | Review org workflow changes, run validation, commit and PR. |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper` | `limen/rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` / `6556758` | unpushed: 1 commit | Push branch and open/update PR for UCC endpoint docs. |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | unknown | n/a | not a Git worktree; Vite cache sample | Classify residue before cleanup. |

## Invariant

Prompt-started work is not garbage. A local root exits this inventory only through a visible
lifecycle event: merged to the default branch, moved into a tracked PR/task, or explicitly
classified with preserved evidence.
