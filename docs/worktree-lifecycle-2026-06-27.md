# Worktree Lifecycle Inventory - 2026-06-27

This inventory records the kept-safe roots under `/Users/4jp/Workspace/.limen-worktrees`.
No directory was deleted or removed during this pass.

Reclaim policy after this audit: a root is reapable only when it is clean, pushed, idle, and
its HEAD is already merged into the remote default branch. Dirty work, unpushed commits,
open/unmerged branches, active roots, and non-Git residue stay visible.

## Summary

- 23 roots inspected.
- 0 roots reclaimed.
- 12 dirty roots: local file changes need review, commit, PR, or explicit discard-after-preserve.
- 7 unpushed roots: local commits need push/PR or absorption into an existing branch.
- 2 non-Git roots: filesystem residue needs classification before any cleanup.
- 2 active roots: freshly opened revenue-ship worktrees are inside the idle grace window.

## Kept Roots

| Root | Repo | Branch / Head | Reason Kept | Next Lifecycle Action |
|---|---|---|---|---|
| `bld-domus-genoma-ci-23a9` | `organvm/domus-genoma` | `limen/bld-domus-genoma-ci-23a9` / `c22646f` | dirty: `.github/workflows/ci.yml` | Review CI workflow, commit if valid, open/update PR. |
| `bld-media-ark-tests-2698` | `organvm/media-ark` | `limen/bld-media-ark-tests-2698` / `2cb3f4d` | dirty: `tests/test_media_ark_process_captures.py` | Review test, run suite, commit and PR. |
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror` | `limen/bld-mirror-mirror-harden-350f` / `9afe14d` | dirty: `api/webhooks/stripe.ts` | Review Stripe hardening, run tests, commit and PR. |
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | `limen/bld-my--father-mother-harden-44b2` / `18730a2` | dirty: `main.py` | Review hardening diff, run tests, commit and PR. |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | `limen/bld-promptscope-next-rev-3fde` / `4fa725b` | dirty: `public/app.js`, `public/index.html`, `src/index.ts` | Review product diff, run build/tests, commit and PR. |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation` | `limen/bld-universal-mail--automation-readme-9031` / `079018c` | dirty: `README.md` | Review README delta, commit and PR. |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter` | `limen/bld2-a-i-chat--exporter-integration-tests-a00b` / `d0d633c` | unpushed: 2 commits | Push branch, open/update PR, or absorb into successor PR. |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine` | `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e` / `be4b920` | dirty: `pyproject.toml` | Review CI fix, run tests, commit and PR. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | `limen/cifix-organvm-i-theoria-hierarchia-mundi-3145` / `677df2b` | dirty: package files and `tests/` | Review CI/test diff, run suite, commit and PR. |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles` | `limen/discover-organvm-kerygma-profiles-6c74` / `a8a029f` | dirty: generated `egg-info` and `__pycache__` | Confirm generated-only dirt, then clean via project-safe ignore/cleanup. |
| `exporter-mp` | `organvm/a-i-chat--exporter` | `limen/exporter-multiprovider` / `6c88427` | unpushed: 2 commits, no upstream | Push branch and open PR for multiprovider work. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | `limen/gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` / `80e7617` | dirty: generated structure-test results | Classify generated result drift, commit only if intended. |
| `gen-organvm-mirror-mirror-security-0622-c552` | `organvm/mirror-mirror` | `limen/gen-organvm-mirror-mirror-security-0622-c552` / `afed90a` | unpushed: local security commit | Push branch, open/update PR, or absorb into current security PR. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | unknown | n/a | not a Git worktree; empty sample | Classify residue before cleanup. |
| `gen-organvm-the-invisible-ledger-security-0622-d8f8` | `organvm/the-invisible-ledger` | `limen/sec-audit-0622` / `b208078` | unpushed: local security commit | Push branch, open/update PR, or absorb into current security PR. |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | `limen/gen-organvm-universal-mail--automation-test-coverage-0625-151e` / `bff9ae1` | dirty: broad deletion set | High-risk review before any action; preserve until root cause is known. |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons` | `limen/gh-organvm-object-lessons-19-605a` / `cf89af6` | unpushed: 2 commits | Push branch and open/update PR for Letterboxd ingestion work. |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `organvm/the-invisible-ledger` | `limen/resolve-a-organvm-the-invisible-ledger-4-f657` / `1741370` | unpushed: 1 commit | Push branch and open/update PR for PostgreSQL adapter work. |
| `resolve-organvm-i-theoria-.github-459-1ade` | `organvm/.github` | `limen/resolve-organvm-i-theoria-.github-459-1ade` / `efff71c` | dirty: workflows, dashboard types, `tsconfig.json` | Review org workflow changes, run validation, commit and PR. |
| `rev-organvm-mirror-mirror-revenue-ship-0627-ad5e` | `organvm/mirror-mirror` | `limen/rev-organvm-mirror-mirror-revenue-ship-0627-ad5e` / `1668f71` | active: clean worktree inside 6h idle grace | Let the active dispatch run; harvest/verify before any cleanup. |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper` | `limen/rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` / `6556758` | unpushed: 1 commit | Push branch and open/update PR for UCC endpoint docs. |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | unknown | n/a | not a Git worktree; Vite cache sample | Classify residue before cleanup. |
| `rev-organvm-universal-mail--automation-revenue-ship-0627-da5e` | `organvm/universal-mail--automation` | `limen/rev-organvm-universal-mail--automation-revenue-ship-0627-da5e` / `c319a96` | active: clean worktree inside 6h idle grace | Let the active dispatch run; harvest/verify before any cleanup. |

## Invariant

Prompt-started work is not garbage. A local root exits this inventory only through a visible
lifecycle event: merged to the default branch, moved into a tracked PR/task, or explicitly
classified with preserved evidence.
