# Canonical Worktree Lifecycle Ledger

Last audited: 2026-06-27 from `/Users/4jp/Workspace/limen`.

This is the canonical working ledger for roots under
`/Users/4jp/Workspace/.limen-worktrees`. A root exits this ledger only through a
visible lifecycle receipt:

- merged or patch-equivalent on the remote default branch;
- open PR or pushed preserve branch;
- explicit blocker/task record naming the retained work;
- documented non-source residue classification.

No directory was deleted or removed during this ledger pass.

## Current Scan

Evidence commands:

- `python3 scripts/worktree-debt.py --json`: 20 roots, 12 debt-bearing roots after the
  domus-genoma CI PR preservation and a new dispatcher reservation root.
- per-root `git status --porcelain`, `git log --oneline -5`, `git cherry <default> HEAD`.
- non-Git residue inspection with `find` and direct reads of cache metadata files.

Current classes:

- 8 dirty working trees counted as debt.
- 0 unique local-only unpushed roots among the completed drain roots; newly spawned
  dispatcher roots are inside the active grace window.
- 2 non-Git residue roots.
- 8 active roots, including freshly pushed draft-PR roots and one new dispatcher root
  still inside the idle grace window.
- 2 clean roots not merged to default, both with draft PR receipts.
- 0 content-preserved roots remain on disk; two were reclaimed by the background
  reaper after their content-preserved classification was visible.

System pothole found during this pass: none of the 20 root slugs appear directly
in `tasks.yaml`. The strongest origin receipt for most roots is therefore the
root/branch slug plus repo and recent commit/PR context, not a task-board entry.
That is not enough for a fully automatic lifecycle.

## Ledger

| Root | Repo | State | Origin Receipt | Evidence | Disposition | Next Action |
|---|---|---|---|---|---|---|
| `bld-domus-genoma-ci-23a9` | `organvm/domus-genoma` | draft PR open | branch `limen/bld-domus-genoma-ci-23a9`; likely build/CI task; no exact task slug in board | clean; PR [#144](https://github.com/organvm/domus-genoma/pull/144); commit `c53a571`; untracked CI draft was rebased onto current `origin/master`; YAML parse passed; `git diff --check origin/master..HEAD` passed; `just --dry-run check-all` now shows `shfmt -d` and no `shfmt -w`; `just fmt-check` passed; full local `just check-all` exposed pre-existing BATS failures | preserved outside local disk, active grace; lifecycle remains open until merged or explicitly superseded | Review PR CI and the known pre-existing BATS blockers, then merge or supersede by named branch/PR. |
| `bld-media-ark-tests-2698` | `organvm/media-ark` | draft PR open | branch `limen/bld-media-ark-tests-2698`; likely tests task; no exact task slug in board | clean; PR [#50](https://github.com/organvm/media-ark/pull/50); commit `b7509dc`; stale untracked test draft was ported into `tests/test_process_captures_core.py`; `npm test` passed 98 tests; `npm run release:verify` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review and merge the capture/platform test-contract PR, or supersede by a named successor that preserves this coverage. |
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror` | dirty | branch `limen/bld-mirror-mirror-harden-350f`; likely hardening task; no exact task slug in board | HEAD `9afe14d`; default `origin/main`; modified `api/webhooks/stripe.ts`; ahead 0 | lifecycle debt | Review Stripe hardening, run tests, then commit/push/PR. |
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | dirty | branch `limen/bld-my--father-mother-harden-44b2`; likely hardening task; no exact task slug in board | HEAD `18730a2`; default `origin/main`; modified `main.py`; ahead 0 | lifecycle debt | Review hardening diff, run tests, then commit/push/PR. |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | dirty | branch `limen/bld-promptscope-next-rev-3fde`; likely next-revenue task; no exact task slug in board | HEAD `4fa725b`; modified `public/app.js`, `public/index.html`, `src/index.ts`; ahead 0 | lifecycle debt | Review product delta, run build/tests, then commit/push/PR. |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation` | draft PR open | branch `limen/bld-universal-mail--automation-readme-9031`; likely README task; no exact task slug in board | clean; PR [#108](https://github.com/organvm/universal-mail--automation/pull/108); commit `29f6b4b`; README marker check passed; `python3 cli.py -h` passed; `python3 -m py_compile cli.py api/app.py api/plans.py mcp_server/server.py` passed; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_config.py tests/test_models.py tests/test_rules.py tests/test_web.py` passed 158 tests | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review README modernization and merge, or supersede by a named successor that preserves this content. |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter` | draft PR open | branch `limen/bld2-a-i-chat--exporter-integration-tests-a00b`; likely integration-tests task; no exact task slug in board | clean; PR [#96](https://github.com/organvm/a-i-chat--exporter/pull/96); commits `6d73e1a`, `d0d633c`; `pnpm test` passed; `pnpm lint` passed with warnings; branch was 32 behind `origin/master` at preservation time | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review freshness/CI, then merge or name a successor PR that absorbed both commits. |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine` | dirty | branch `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e`; likely CI-fix task; no exact task slug in board | HEAD `be4b920`; modified `pyproject.toml`; ahead 0 | lifecycle debt | Review dependency/CI fix, run tests, then commit/push/PR. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | dirty | branch `limen/cifix-organvm-i-theoria-hierarchia-mundi-3145`; likely CI/test task; no exact task slug in board | HEAD `677df2b`; modified package files plus untracked `tests/`; ahead 0 | lifecycle debt | Review implementation and tests together, run suite, then commit/push/PR. |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles` | draft PR open | branch `limen/discover-organvm-kerygma-profiles-6c74`; discovery task; no exact task slug in board | clean; PR [#8](https://github.com/organvm/kerygma-profiles/pull/8); commits `a8a029f`, `d7fd19e`; generated files remain on disk but are ignored; `python3 -m pytest` passed 24 tests; `python3 -m ruff check .` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review and merge the generated-artifact hygiene PR, or supersede by a named successor. |
| `exporter-mp` | `organvm/a-i-chat--exporter` | draft PR open | branch `limen/exporter-multiprovider`; explicit multiprovider branch; no exact task slug in board | clean; PR [#95](https://github.com/organvm/a-i-chat--exporter/pull/95); commits `5c3298b`, `6c88427`, `dd73cce`; `pnpm test` passed; `pnpm lint` passed with warnings after lint-setup compatibility fix | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review provider behavior and CI, then merge or supersede by named branch/PR. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | dirty generated results | branch `limen/gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38`; generated CI-green task; no exact task slug in board | HEAD `80e7617`; modified `structure-tests/results/ex01` through `ex11`; ahead 0 | lifecycle debt | Classify result drift; commit only if these are intended refreshed fixtures. |
| `gen-organvm-limen-typing-0627-ccac` | `organvm/limen` | active dirty | branch `limen/gen-organvm-limen-typing-0627-ccac`; generated typing task reserved during this cleanup | HEAD `b2c6398` at `origin/main`; modified `cli/src/limen/capacity.py`, `cli/src/limen/converge.py`, `cli/src/limen/vigilia/params.py`; inside active grace window | active grace, not counted as debt yet | Let the dispatched session finish; if it stalls, preserve the diff with tests and a PR or record a blocker. |
| `gen-organvm-mirror-mirror-security-0622-c552` | `organvm/mirror-mirror` | reclaimed, content-preserved | branch `limen/gen-organvm-mirror-mirror-security-0622-c552`; generated security task; no exact task slug in board | prior evidence: clean HEAD `afed90a`; `git cherry origin/main HEAD` patch-equivalent (`- afed90a...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value on default branch. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | unknown | non-Git residue | root slug says generated CI-green for `the-invisible-ledger`; no git metadata or exact board slug | contains only empty `dist/` directory; no files | documented non-source residue | No unique artifact to preserve. Reclaimable only after operator acceptance; no deletion in this pass. |
| `gen-organvm-the-invisible-ledger-security-0622-d8f8` | `organvm/the-invisible-ledger` | reclaimed, content-preserved | branch `limen/sec-audit-0622`; generated security task; merged as PR #30 per prior audit | prior evidence: clean HEAD `b208078`; `git cherry origin/main HEAD` patch-equivalent (`- b208078...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value beyond merged PR #30. |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | dirty, high risk | branch `limen/gen-organvm-universal-mail--automation-test-coverage-0625-151e`; generated test-coverage task; no exact task slug in board | HEAD `bff9ae1`; 171 deletions including docs, package files, source, workflows; ahead 0 | freeze as dangerous lifecycle debt | Do not clean/reset casually. First determine whether this is an incomplete checkout, generated deletion bug, or intentional migration; preserve exact diff/blocker before action. |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons` | draft PR open | branch `limen/gh-organvm-object-lessons-19-605a`; GitHub issue/root slug; no exact task slug in board | clean; PR [#22](https://github.com/organvm/object-lessons/pull/22); ahead 2: `f597500`, `cf89af6`; `npm run validate` passed; `git diff --check origin/main..HEAD` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review ingestion fixtures/full build, then merge or supersede by named branch/PR. |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `organvm/the-invisible-ledger` | active clean | branch `limen/resolve-a-organvm-the-invisible-ledger-4-f657`; issue resolution task | clean at `origin/main` HEAD `2e785e4`; old local PostgreSQL adapter tip preserved as `preserve/resolve-a-organvm-the-invisible-ledger-4-f657-1741370` | active grace, not debt | Re-check after idle window; open no duplicate PR unless audit finds missing value beyond landed adapter/billing work. |
| `resolve-organvm-i-theoria-.github-459-1ade` | `organvm/.github` | dirty | branch `limen/resolve-organvm-i-theoria-.github-459-1ade`; organization issue resolution task; no exact task slug in board | HEAD `efff71c`; modified workflows, untracked `src/automation/dashboard/types/`, `tsconfig.json`; ahead 0 | lifecycle debt | Review org workflow/dashboard changes, run validation, then commit/push/PR. |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper` | draft PR open | branch `limen/rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f`; revenue-readiness task; no exact task slug in board | clean; PR [#328](https://github.com/organvm/public-record-data-scrapper/pull/328); ahead 1: `6556758`; `yamljs` parsed `server/openapi.yaml` and found `/api/scrape/ucc`; `git diff --check origin/main..HEAD` passed | preserved outside local disk, still lifecycle debt until merged or explicitly superseded | Review API docs, then merge or supersede by named branch/PR. |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | unknown | non-Git residue | root slug says revenue-readiness for `the-invisible-ledger`; no git metadata or exact board slug | contains `.vite/deps/_metadata.json` with empty optimized/chunks and `.vite/deps/package.json` with `type: module` | documented cache-only residue | No unique source artifact to preserve. Reclaimable only after operator acceptance; no deletion in this pass. |

## Roadblocks And Potholes

- Worktree roots are not task-board addressable. The board has repo/task context, but the exact
  root slug is absent for all 20 current roots.
- Non-Git residue bypasses git lifecycle checks. The two `the-invisible-ledger`
  residue roots needed direct filesystem inspection to classify.
- Patch-equivalent work looked unpushed until the debt scanner learned `git cherry`
  equivalence. That created false debt pressure around merged/squashed work.
- The first four unique local-only roots are now remote-preserved as draft PRs, but
  the scanner correctly keeps them in lifecycle debt until merge or named supersession.
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
  broad deletes with no ahead commits. It should be handled before routine generated
  build-out resumes.

## Drain Order

1. Close the two non-Git residue roots by keeping this classification visible; remove
   only after explicit operator acceptance or a scripted reclaim gate that records the
   classification.
2. Drive the eight draft PR receipts to merge or named supersession:
   [domus-genoma#144](https://github.com/organvm/domus-genoma/pull/144),
   [a-i-chat--exporter#96](https://github.com/organvm/a-i-chat--exporter/pull/96),
   [a-i-chat--exporter#95](https://github.com/organvm/a-i-chat--exporter/pull/95),
   [object-lessons#22](https://github.com/organvm/object-lessons/pull/22),
   [public-record-data-scrapper#328](https://github.com/organvm/public-record-data-scrapper/pull/328),
   [kerygma-profiles#8](https://github.com/organvm/kerygma-profiles/pull/8), and
   [universal-mail--automation#108](https://github.com/organvm/universal-mail--automation/pull/108),
   plus [media-ark#50](https://github.com/organvm/media-ark/pull/50).
3. Work the dirty roots from lowest risk to highest risk: generated-only caches,
   single-file deltas, multi-file implementation deltas, then the broad deletion root.
4. Reclaim the two content-preserved roots only after the ledger/acceptance receipt is
   committed and the operator agrees.
