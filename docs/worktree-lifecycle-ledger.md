# Canonical Worktree Lifecycle Ledger

Last audited: 2026-06-27 from `/Users/4jp/Workspace/limen`.

This is the canonical working ledger for roots under
`/Users/4jp/Workspace/.limen-worktrees`. A root exits this ledger only through a
visible lifecycle receipt:

- merged or patch-equivalent on the remote default branch;
- open PR or pushed preserve branch;
- explicit blocker/task record naming the retained work;
- documented non-source residue classification.

Five duplicate local checkout directories were removed during the follow-up pass
only after their local `HEAD` matched the fetched remote PR head exactly:
`bld-domus-genoma-ci-23a9`, `bld-media-ark-tests-2698`,
`bld-universal-mail--automation-readme-9031`,
`bld2-a-i-chat--exporter-integration-tests-a00b`, and `exporter-mp`.
The unique work remains preserved on the remote branches and open draft PRs.

## Current Scan

Evidence commands:

- `python3 scripts/worktree-debt.py --json`: 14 roots, 10 debt-bearing roots after five
  duplicate PR-preserved local worktrees were removed from `.limen-worktrees`.
- per-root `git status --porcelain`, `git log --oneline -5`, `git cherry <default> HEAD`.
- non-Git residue inspection with `find` and direct reads of cache metadata files.

Current classes:

- 2 dirty working trees counted as debt.
- 3 local unpushed or remote-mismatched commit roots.
- 2 non-Git residue roots.
- 3 active roots inside the idle grace window.
- 3 clean roots not merged to default, with draft PR receipts.
- 1 clean, merged, idle root.
- 5 remote-preserved draft-PR checkouts removed from local scan after exact
  local/remote commit equality was verified.

System pothole found during this pass: none of the 14 current root slugs appear directly
in `tasks.yaml`. The strongest origin receipt for most roots is therefore the
root/branch slug plus repo and recent commit/PR context, not a task-board entry.
That is not enough for a fully automatic lifecycle.

## Ledger

| Root | Repo | State | Origin Receipt | Evidence | Disposition | Next Action |
|---|---|---|---|---|---|---|
| `bld-domus-genoma-ci-23a9` | `organvm/domus-genoma` | local checkout removed; draft PR open | branch `limen/bld-domus-genoma-ci-23a9`; likely build/CI task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `c53a571`; PR [#144](https://github.com/organvm/domus-genoma/pull/144); untracked CI draft was rebased onto current `origin/master`; YAML parse passed; `git diff --check origin/master..HEAD` passed; `just --dry-run check-all` now shows `shfmt -d` and no `shfmt -w`; `just fmt-check` passed; full local `just check-all` exposed pre-existing BATS failures | remote PR preserved; no local debt root remains | Review PR CI and the known pre-existing BATS blockers, then merge or supersede by named branch/PR. Recreate a local worktree from the branch only if needed. |
| `bld-media-ark-tests-2698` | `organvm/media-ark` | local checkout removed; draft PR open | branch `limen/bld-media-ark-tests-2698`; likely tests task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `b7509dc`; PR [#50](https://github.com/organvm/media-ark/pull/50); stale untracked test draft was ported into `tests/test_process_captures_core.py`; `npm test` passed 98 tests; `npm run release:verify` passed | remote PR preserved; no local debt root remains | Review and merge the capture/platform test-contract PR, or supersede by a named successor that preserves this coverage. Recreate a local worktree from the branch only if needed. |
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror` | draft PR open | branch `limen/bld-mirror-mirror-harden-350f`; likely hardening task; no exact task slug in board | clean; PR [#67](https://github.com/organvm/mirror-mirror/pull/67); commit `f44da8e`; branch was rebased onto `origin/main` `af0f15b`; remote branch was updated with an explicit force-with-lease from stale head `3d822c6`; local checks passed: focused ESLint on `api/webhooks/stripe.ts`, `api/lib/webhook.ts`, and `src/__tests__/stripeWebhook.test.ts`; targeted Stripe webhook tests passed 4 tests; scoped TypeScript check passed; `npm test` passed 203 tests; `npm run build` passed with existing CSS/chunk/deprecation warnings; GitHub CI `Lint, build & test` passed; PR merge state `CLEAN` | preserved outside local disk, active grace; lifecycle remains open until merged or explicitly superseded | Review and merge PR #67, or supersede by named branch/PR that preserves this webhook hardening. |
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | draft PR open | branch `limen/bld-my--father-mother-harden-44b2`; likely hardening task; no exact task slug in board | clean at commit `ff5d36d`; draft PR [#28](https://github.com/organvm/my--father-mother/pull/28); local predicate passed `python3 -m py_compile main.py` and `python3 -m pytest -q` (99 passed); PR merge state currently `UNSTABLE` because it was preserved from an older base | remote PR preserved; lifecycle remains open until merged or explicitly superseded | Rebase/retest PR #28 or supersede by a named branch that preserves the request-validation and structured-logging hardening. |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | draft PR open | branch `limen/bld-promptscope-next-rev-3fde`; likely next-revenue task; no exact task slug in board | clean at commit `362ec18`; draft PR [#15](https://github.com/organvm/promptscope/pull/15); local source checks passed `node --check public/app.js`, TypeScript source check with `--skipLibCheck`, and `git diff --check`; declared `npm run typecheck` is blocked by existing `@cloudflare/workers-types` / `lib.webworker` declaration conflicts; PR merge state currently `DIRTY` because it was preserved from an older base | remote PR preserved; lifecycle remains open until merged or explicitly superseded | Rebase/retest PR #15 or supersede by a named branch that preserves the account dashboard and `/api/account` surface. |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation` | local checkout removed; draft PR open | branch `limen/bld-universal-mail--automation-readme-9031`; likely README task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `29f6b4b`; PR [#108](https://github.com/organvm/universal-mail--automation/pull/108); README marker check passed; `python3 cli.py -h` passed; `python3 -m py_compile cli.py api/app.py api/plans.py mcp_server/server.py` passed; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_config.py tests/test_models.py tests/test_rules.py tests/test_web.py` passed 158 tests | remote PR preserved; no local debt root remains | Review README modernization and merge, or supersede by a named successor that preserves this content. Recreate a local worktree from the branch only if needed. |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter` | local checkout removed; draft PR open | branch `limen/bld2-a-i-chat--exporter-integration-tests-a00b`; likely integration-tests task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `d0d633c`; PR [#96](https://github.com/organvm/a-i-chat--exporter/pull/96); commits `6d73e1a`, `d0d633c`; `pnpm test` passed; `pnpm lint` passed with warnings; branch was 32 behind `origin/master` at preservation time | remote PR preserved; no local debt root remains | Review freshness/CI, then merge or name a successor PR that absorbed both commits. Recreate a local worktree from the branch only if needed. |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine` | draft PR open | branch `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e`; likely CI-fix task; no exact task slug in board | clean; PR [#60](https://github.com/organvm/conversation-corpus-engine/pull/60); commit `0f96c88`; rebased onto `origin/main` `bebe0d4`; local checks passed: `python3 -m pip install -e ".[dev]"`, `python3 -m pytest tests/ -v --tb=short` (351 passed), `python3 -m ruff check src/ tests/`, `python3 -m ruff format --check src/ tests/`, schema import command; GitHub CI and CodeQL passed; merge state `CLEAN` | preserved outside local disk, active grace; lifecycle remains open until merged or explicitly superseded | Review and merge PR #60, or supersede by named branch/PR. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | dirty local checkout; superseded upstream | branch `limen/cifix-organvm-i-theoria-hierarchia-mundi-3145`; likely CI/test task; no exact task slug in board | HEAD `677df2b`; dirty smoke-test/root-fix draft; `origin/main` at `9f26d55` already contains `tests/test_smoke.py` plus broader `tests/test_loader.py` and `tests/test_cli.py`; upstream files also include the Ruff import/unused-import cleanup this root was carrying | remote/default supersession receipt in `docs/worktree-preservation-receipts.json`; no PR needed | Reclaim only after normal operator acceptance; do not dispatch this stale root as unique work. |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles` | draft PR open | branch `limen/discover-organvm-kerygma-profiles-6c74`; discovery task; no exact task slug in board | clean; PR [#8](https://github.com/organvm/kerygma-profiles/pull/8); commits `a8a029f`, `d7fd19e`; generated files remain on disk but are ignored; `python3 -m pytest` passed 24 tests; `python3 -m ruff check .` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review and merge the generated-artifact hygiene PR, or supersede by a named successor. |
| `exporter-mp` | `organvm/a-i-chat--exporter` | local checkout removed; draft PR open | branch `limen/exporter-multiprovider`; explicit multiprovider branch; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `dd73cce`; PR [#95](https://github.com/organvm/a-i-chat--exporter/pull/95); commits `5c3298b`, `6c88427`, `dd73cce`; `pnpm test` passed; `pnpm lint` passed with warnings after lint-setup compatibility fix | remote PR preserved; no local debt root remains | Review provider behavior and CI, then merge or supersede by named branch/PR. Recreate a local worktree from the branch only if needed. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | dirty generated results; private patch preserved | branch `limen/gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38`; generated CI-green task; no exact task slug in board | HEAD `80e7617`; 11 modified `structure-tests/results/ex01` through `ex11`; exact generated-results patch preserved in `docs/worktree-preservation-receipts.json` with SHA-256 `92dc514490c7bbf3c6a14eb3889656563d070a23af55af3d64f2a16999d63bc9`; repo README says no live URL, installable package, runnable release, or documented execution path | owner blocker; do not publish as source change until classified | Classify whether these generated structure-test results should be refreshed from the current corpus before cleanup, PR creation, or delegation. |
| `gen-organvm-mirror-mirror-security-0622-c552` | `organvm/mirror-mirror` | reclaimed, content-preserved | branch `limen/gen-organvm-mirror-mirror-security-0622-c552`; generated security task; no exact task slug in board | prior evidence: clean HEAD `afed90a`; `git cherry origin/main HEAD` patch-equivalent (`- afed90a...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value on default branch. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | unknown | non-Git residue | root slug says generated CI-green for `the-invisible-ledger`; no git metadata or exact board slug | contains only empty `dist/` directory; no files; receipt in `docs/worktree-preservation-receipts.json` | documented non-source residue | No unique artifact to preserve. Reclaimable only after operator acceptance; no deletion in this pass. |
| `gen-organvm-the-invisible-ledger-security-0622-d8f8` | `organvm/the-invisible-ledger` | reclaimed, content-preserved | branch `limen/sec-audit-0622`; generated security task; merged as PR #30 per prior audit | prior evidence: clean HEAD `b208078`; `git cherry origin/main HEAD` patch-equivalent (`- b208078...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value beyond merged PR #30. |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | dirty, high risk; private patch preserved | branch `limen/gen-organvm-universal-mail--automation-test-coverage-0625-151e`; generated test-coverage task; no exact task slug in board | HEAD `bff9ae1`; 167 tracked deletions including docs, package files, source, workflows; ahead 0; private preservation receipt `docs/worktree-preservation-receipts.json` records patch SHA-256 `01f1705aaa210e3c42944f228e371e6d81547fd8ab93becd6ce701ce9a126760`; untracked material classified as generated `.venv`/`__pycache__` residue | owner blocker; do not reclaim or dispatch over this root | Classify whether this is an incomplete checkout, generated deletion bug, or intentional migration before cleanup, PR creation, or delegation. |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons` | draft PR open | branch `limen/gh-organvm-object-lessons-19-605a`; GitHub issue/root slug; no exact task slug in board | clean; PR [#22](https://github.com/organvm/object-lessons/pull/22); ahead 2: `f597500`, `cf89af6`; `npm run validate` passed; `git diff --check origin/main..HEAD` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review ingestion fixtures/full build, then merge or supersede by named branch/PR. |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `organvm/the-invisible-ledger` | active clean | branch `limen/resolve-a-organvm-the-invisible-ledger-4-f657`; issue resolution task | clean at `origin/main` HEAD `2e785e4`; old local PostgreSQL adapter tip preserved as `preserve/resolve-a-organvm-the-invisible-ledger-4-f657-1741370` | active grace, not debt | Re-check after idle window; open no duplicate PR unless audit finds missing value beyond landed adapter/billing work. |
| `resolve-organvm-i-theoria-.github-459-1ade` | `organvm/.github` | local commit preserved; remote history mismatch | branch `limen/resolve-organvm-i-theoria-.github-459-1ade`; organization issue resolution task; no exact task slug in board | local commit `0035dff`; exact patch preserved in `docs/worktree-preservation-receipts.json` with SHA-256 `020b4c9e8227d560caa10714aac24376e56dea272de3563af7211b4d3b0f4a25`; workflow YAML parse passed; `npm exec --yes --package typescript@5.6.3 -- tsc -p tsconfig.json` passed; `npm test` and `npm run build` are configured no-op predicates; direct push failed, then `origin/main` force-updated to unrelated current history `e334fb0`, where the touched workflow files are absent | owner blocker; do not dispatch as a normal PR branch | Classify this patch against the current `organvm/.github` default branch before cleanup or delegation; direct PR is blocked by remote history/file mismatch. |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper` | draft PR open | branch `limen/rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f`; revenue-readiness task; no exact task slug in board | clean; PR [#328](https://github.com/organvm/public-record-data-scrapper/pull/328); ahead 1: `6556758`; `yamljs` parsed `server/openapi.yaml` and found `/api/scrape/ucc`; `git diff --check origin/main..HEAD` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review API docs, then merge or supersede by named branch/PR. |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | unknown | non-Git residue | root slug says revenue-readiness for `the-invisible-ledger`; no git metadata or exact board slug | contains `.vite/deps/_metadata.json` with empty optimized/chunks and `.vite/deps/package.json` with `type: module`; receipt in `docs/worktree-preservation-receipts.json` | documented cache-only residue | No unique source artifact to preserve. Reclaimable only after operator acceptance; no deletion in this pass. |

## Roadblocks And Potholes

- Worktree roots are not task-board addressable. The board has repo/task context, but the exact
  root slug is absent for all 14 current scanned roots.
- Non-Git residue bypasses git lifecycle checks. The two `the-invisible-ledger`
  residue roots needed direct filesystem inspection to classify.
- Patch-equivalent work looked unpushed until the debt scanner learned `git cherry`
  equivalence. That created false debt pressure around merged/squashed work.
- The latest single-file dirty root is now remote-preserved as draft PR
  [mirror-mirror#67](https://github.com/organvm/mirror-mirror/pull/67), and the
  scanner now classifies it as active instead of dirty debt.
- Five clean, duplicate local checkouts had open draft PRs with exact local/remote
  commit equality. Removing those local checkout copies dropped the scanner from
  19 roots / 16 debt to 14 roots / 11 debt without deleting unique work.
- The automated beat reclaimed two content-preserved roots immediately after classification.
  That did not lose unique source, but it was too eager for the current operator-acceptance
  posture; `scripts/drain.sh` now requires `LIMEN_RECLAIM_APPLY=1` for future removals.
- Dirty roots at default HEAD carry invisible work as uncommitted filesystem
  deltas. They need receipts before the system can reclaim or dispatch around them.
- `dispatch-parallel` can create and retire active roots while cleanup is reducing
  old lifecycle debt. That keeps the stream alive, but it can mask whether the
  system is actually draining net debt unless the final scan is authoritative.
- `domus-genoma` CI hardening surfaced pre-existing local `just check-all`
  failures: Brewfile manifest drift for `block-goose-cli`, a `#!/bin/bash`
  shebang in `lint_test.sh`, and multiple desktop-router BATS route failures.
- The Universal Mail Automation test-coverage root is a dangerous deletion shape:
  broad deletes with no ahead commits. A private patch receipt now preserves the exact
  deletion diff; it still needs owner classification before routine generated build-out resumes.

## Drain Order

1. Close the two non-Git residue roots by keeping this classification visible; remove
   only after explicit operator acceptance or a scripted reclaim gate that records the
   classification.
2. Drive the ten draft PR receipts to merge or named supersession:
   [domus-genoma#144](https://github.com/organvm/domus-genoma/pull/144),
   [mirror-mirror#67](https://github.com/organvm/mirror-mirror/pull/67),
   [conversation-corpus-engine#60](https://github.com/organvm/conversation-corpus-engine/pull/60),
   [a-i-chat--exporter#96](https://github.com/organvm/a-i-chat--exporter/pull/96),
   [a-i-chat--exporter#95](https://github.com/organvm/a-i-chat--exporter/pull/95),
   [object-lessons#22](https://github.com/organvm/object-lessons/pull/22),
   [public-record-data-scrapper#328](https://github.com/organvm/public-record-data-scrapper/pull/328),
   [kerygma-profiles#8](https://github.com/organvm/kerygma-profiles/pull/8), and
   [universal-mail--automation#108](https://github.com/organvm/universal-mail--automation/pull/108),
   plus [media-ark#50](https://github.com/organvm/media-ark/pull/50).
3. Work the dirty roots from lowest risk to highest risk: generated-only caches,
   remaining single-file deltas, multi-file implementation deltas, then the broad deletion root.
4. Keep the historical content-preserved reclaims visible as receipts; do not
   perform further local removals unless the target has exact remote/default
   preservation or explicit operator acceptance.
