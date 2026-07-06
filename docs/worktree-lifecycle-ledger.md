# Canonical Worktree Lifecycle Ledger

Last audited: 2026-07-06 from `/Users/4jp/Workspace/limen`.

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

2026-07-06 org-health first-slice residue pass:

- Selected conductor packet `tranche-org-health-organ-firstslice-0704-aac2b482`.
- Read-only inspection of
  `/Users/4jp/Workspace/.limen-worktrees/org-health-organ-firstslice-0704-aac2b482`
  found no `.git` metadata and no owner source files. The root contains only
  `logs/session-lifecycle-pressure.json` (1,237 bytes, SHA-256
  `4cad9d67c495f4bdd076b7fb985ab26b3f2d179ca998cd3577a216a3f134b399`) and
  `logs/session-lifecycle-pressure.md` (193 bytes, SHA-256
  `f7796610ac423010cd88a9a9e516eebf1ccfac4ffa09337a9e04502cfb1a0c3e`).
- Added a `documented-residue` receipt for `org-health-organ-firstslice-0704-aac2b482` in
  `docs/worktree-preservation-receipts.json`. This records a non-source residue proof only:
  no local reclaim, deletion, force-push, merge, task-board mutation, or owner-repo source edit
  was performed.

2026-07-06 remote-supersession pass:

- `python3 scripts/worktree-debt.py --json` initially reported 48 roots with 1 debt-bearing
  root: `linear-conjuring-bear`, classified as `not-merged-to-default`.
- Read-only inspection found branch `session/post-moneta-durability` at
  `01c7773cd42adf2e9a3c4277bb635bc1a53eaf3f`, preserved by draft PR
  [#635](https://github.com/organvm/limen/pull/635), but the PR is `CONFLICTING` and not
  merge-ready.
- The branch is superseded by current `origin/main`: commit `21ba3f3b` already staged the
  consolidation execution packet under `docs/consolidation/EXECUTION-MANIFEST.md` and
  `scripts/consolidation-*-apply.sh`; current main's scripts retain the explicit
  `LIMEN_CONSOLIDATION_GATE=consolidation-gate-open` hard gate, while the draft branch's copies
  remove that guard. Main also carries the richer `docs/session-2026-07-03-audit-trail.md`.
- Added a `remote-superseded` receipt for `linear-conjuring-bear` in
  `docs/worktree-preservation-receipts.json`. No PR was merged or closed, no branch was deleted,
  no local checkout was removed, and no GitHub consolidation command was run.
- Re-run proof after the receipt: `python3 scripts/worktree-debt.py --fail-over-cap` reports
  0 debt roots / 49 scanned roots, with `linear-conjuring-bear` classified as
  `remote-superseded`.
- Also classified active root `fluttering-twirling-abelson` as default-branch-preserved:
  local `HEAD` `034ab5f61f364f4acd99266a10fc00de856698da` is an ancestor of current
  `origin/main` `b80e782aa0c93f5d5cca4c57bed82bc8d390e993`, and
  `git diff origin/main...HEAD` is empty. No PR was opened, no branch was pushed, and no local
  checkout was removed.

2026-07-04 lifecycle closeout pass:

- `python3 scripts/worktree-debt.py --json`: 77 roots, 0 debt-bearing roots, cap 12.
- Current class mix: 34 documented residue roots, 15 open-PR remote-preserved roots,
  8 remote-merged/default-preserved roots, 8 owner-blocker roots, and 12 active roots under grace
  windows.
- Classified 34 `not-a-git-dir` roots as documented non-source residue after read-only inspection.
  Every classified path contains exactly two files, `logs/session-lifecycle-pressure.json` and
  `logs/session-lifecycle-pressure.md`, and no Git metadata or source files. Exact byte counts and
  SHA-256 hashes are recorded in `docs/worktree-preservation-receipts.json`.
- Classified `feat+workstream-channels` as remote-preserved by draft PR
  [#634](https://github.com/organvm/limen/pull/634). Local `HEAD`
  `dc0498d192c2aa76bf98d1b7fa0dda496baf3c8b` equals `origin/heal/revive-self-heal-beat`
  and the PR `headRefOid`; the scanner now reports this root as `remote-pr-open`.
- Classified `agent-aefc63d95daa3131b` as an owner blocker, not reclaimable lifecycle residue.
  Local `HEAD` `d45b030d1427826c1c0c54b3cb54d552b94104a0` equals
  `origin/work/photos-universe-20260629-182431`; PR
  [#497](https://github.com/organvm/limen/pull/497) is closed unmerged. The private proof receipt
  is recorded under
  `.limen-private/session-corpus/lifecycle/worktree-preserve/2026-07-04T184224Z-agent-aefc63d95daa3131b/receipt.json`.
- Classified `gh-organvm-domus-genoma-170-bbbc` as default-branch-preserved. Local `HEAD`
  `24a251c550c438f90d8e495fdb2b5e62b34a0d22` is an ancestor of `origin/master`
  `97b3f2c6169b83a20e0d1a61ef95b6621d0e1533`; the only dirty item is untracked
  `logs/agents/opencode.json` (293 bytes, SHA-256
  `d476defb235606087f3a33c53eba2fb039086e0c3f91318b335cc7e658a460ff`).
- Classified the final four debt roots:
  `GEN-organvm-limen-ci-green-0702` is preserved by merged PR
  [#574](https://github.com/organvm/limen/pull/574), whose `headRefOid`
  `ced1164444df42fe8fd4b48924bd4f3f420291e7` equals local `HEAD`;
  `peer-audited--behavioral-blockchain`, `review-avditor-billing-pr43`, and
  `wf_29a15be5-9f8-2` have exact private patch receipts under
  `.limen-private/session-corpus/lifecycle/worktree-preserve/` and are now owner blockers rather
  than reclaimable lifecycle residue.
- Closed the stale prompt-index reference `docs-file-fleet-dispatch-lever`: the recorded head
  `1f71ebeffefda1a9f35e3869d9804564f125cf23` is an ancestor of current `origin/main`, and the local
  path no longer exists.
- Closed the stale prompt-index reference `org-social-organ-firstslice-0703-e618`: the recorded
  head `954f36294540` is an ancestor of current `origin/main`, and the local path no longer exists.
- Closed the stale prompt-index reference `org-hr-organ-charter-0704-2089`: the recorded head
  `1f71ebeffefda1a9f35e3869d9804564f125cf23` is an ancestor of current `origin/main`, and the local
  path no longer exists.
- Reaped landed local branch refs `limen/org-hr-organ-charter-0704-2089` and
  `limen/org-social-organ-firstslice-0703-e618` with `python3 scripts/reap-branches.py --apply --force`
  after dry-run proof classified both as `landed-ancestor`.
- Refreshed the prompt lifecycle ledger with remote/cloud receipts enabled:
  `python3 scripts/prompt-lifecycle-ledger.py --write --all`. The private index now has
  `remote.enabled: true` and checked 1000 task PR refs.
- No worktree reclaim, force-push, merge, task-board mutation, or owner-repo source edit was
  performed in this pass.

2026-07-02 live-root reconciliation scan:

- `python3 scripts/worktree-debt.py --json`: 37 roots, 0 debt-bearing roots, cap 12.
- Current class mix: 14 active roots under the grace window, 14 open-PR remote-preserved
  roots, 6 merged-PR repair roots, and 3 owner-blocker roots.
- The seven roots that were debt-bearing at the start of this pass now have owner receipts in
  `docs/worktree-preservation-receipts.json`: six `.limen-repair/pr-*` roots are closed by
  merged Limen PR receipts whose live GitHub `headRefOid` equals local `HEAD`; the
  `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` root is kept visible as an
  owner-blocker because its `.git` file points at missing parent worktree metadata while PR
  #177 remains the owner review surface. A stale prompt-lifecycle remote-branch gap for
  absent root `mirror-mirror` is also closed by the merged PR #87 receipt.
- No local reclaim, deletion, force-push, merge, task-board mutation, or owner-repo source edit
  was performed in this pass.

Newly classified roots:

| Root | Repo | State | Evidence | Disposition | Next Action |
|---|---|---|---|---|---|
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | `organvm/a-i-council--coliseum` | broken Git worktree; owner blocker | `.git` points to missing `/Users/4jp/Workspace/organvm/a-i-council--coliseum/.git/worktrees/gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec`; task `GEN-a-organvm-a-i-council--coliseum-ci-green-0620` is `done` via PR [#177](https://github.com/organvm/a-i-council--coliseum/pull/177); private non-cache file inventory receipt recorded under `.limen-private/session-corpus/lifecycle/worktree-preserve/2026-07-02T220101Z-gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec/receipt.json` | owner-blocker receipt; not cache-only residue | Reclaim only after operator acceptance or after a fresh owner packet verifies PR/default-branch preservation from a valid checkout. |
| `pr-463` | `organvm/limen` | merged PR repair checkout | GitHub PR [#463](https://github.com/organvm/limen/pull/463) is `MERGED`; PR `headRefOid` `adb0911c13a77c9b492ffec1843398f6694b8376` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `pr-466` | `organvm/limen` | merged PR repair checkout | GitHub PR [#466](https://github.com/organvm/limen/pull/466) is `MERGED`; PR `headRefOid` `3f25b5eee2d1964e3ffa68dd2ee42cae6e7ba53c` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `pr-467` | `organvm/limen` | merged PR repair checkout | GitHub PR [#467](https://github.com/organvm/limen/pull/467) is `MERGED`; PR `headRefOid` `ae0568d214a470664dfdca07358e9c7239d84dc8` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `pr-468` | `organvm/limen` | merged PR repair checkout | GitHub PR [#468](https://github.com/organvm/limen/pull/468) is `MERGED`; PR `headRefOid` `117b49213b4fbd77f4ded58e5ee6e09cc0982e54` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `pr-471` | `organvm/limen` | merged PR repair checkout | GitHub PR [#471](https://github.com/organvm/limen/pull/471) is `MERGED`; PR `headRefOid` `73be2bf4b341c5f3d6b2ad3f5bc75c4e955e7074` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `pr-475` | `organvm/limen` | merged PR repair checkout | GitHub PR [#475](https://github.com/organvm/limen/pull/475) is `MERGED`; PR `headRefOid` `63fa4486cb465f63beb0f431e6200a9dfab8d7e6` equals local `HEAD` | remote-merged receipt; no local source debt remains | Reclaim local repair checkout only after normal operator acceptance. |
| `mirror-mirror` | `organvm/mirror-mirror` | absent stale repo-local root; merged PR preserved | prompt-lifecycle index retained `/Users/4jp/Workspace/limen/.worktrees/mirror-mirror`; path is absent from live filesystem and `git worktree list`; GitHub PR [#87](https://github.com/organvm/mirror-mirror/pull/87) is `MERGED` with head `99fdd8d8b49e8a57022e6eec52b706655e973403` | remote-merged receipt; stale remote-branch gap closed | No local source preservation action remains; keep receipt so stale remote scans close. |

2026-06-28 follow-up scan:

- `python3 scripts/worktree-debt.py --json`: 14 roots, 0 debt-bearing roots, cap 12.
- Current class mix: 2 owner-blocker roots, 4 open-PR remote-preserved roots,
  3 documented residues, 2 remote-merged roots, 1 remote-superseded root, and
  2 clean+merged idle roots.
- The raw remote branch receipt still reports 7 present / 4 missing branch names, but the live
  scanner now closes all 4 missing names through owner-blocker, documented-residue,
  remote-superseded, or clean+merged-idle proof; unresolved missing branch gaps are 0.
- No local reclaim, deletion, merge, force-push, or owner-repo source mutation was performed in
  this follow-up. This receipt only updates the owner ledger so the active conductor tranche
  starts from live pressure instead of the older 8-debt summary. Four open draft PR roots now
  report as `remote-pr-open` after confirming their local HEADs exactly match their GitHub PR
  `headRefOid`s; this preserves the source remotely without claiming those PRs are merged or
  ready. Two previously debt-bearing roots now report as `owner-blocker` only because their
  preservation receipts include private patch receipts and SHA-256 evidence; this records
  owner intent and prevents duplicate dispatch, but still requires operator acceptance before
  local reclaim. The Sovereign generated-results root was reclassified as documented non-source
  residue after confirming the checkout is at `origin/main`, the only local deltas are 11
  tracked `structure-tests/results/*.json` snapshots, and the repo README describes the
  project as a parked docs-only shell. The
  Hierarchia root now reports as `remote-superseded` because its dirty import-order draft
  and untracked smoke test are covered by current `origin/main` tests and cleanup. Mirror
  Mirror PR #67 and Public Record Data Scraper PR #328 are now live GitHub `MERGED`
  receipts whose head OIDs match their local worktree heads.
- The active conductor packet is `docs/conductor-tranche.md`:
  `tranche-github-app-limen-bot-not-wired`. Its stop condition forbids creating/installing the
  GitHub App, calling `scripts/set-credential.sh`, writing PEM/key material, or changing GitHub
  secrets without explicit human approval.

Current live roots by scanner reason:

| Root | Scanner reason | Debt |
|---|---|---|
| `bld-mirror-mirror-harden-350f` | `remote-merged` | no |
| `bld-my--father-mother-harden-44b2` | `remote-pr-open` | no |
| `bld-promptscope-next-rev-3fde` | `remote-pr-open` | no |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `remote-pr-open` | no |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `remote-superseded` | no |
| `discover-organvm-kerygma-profiles-6c74` | `remote-pr-open` | no |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `documented-residue` | no |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | `documented-residue` | no |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `owner-blocker` | no |
| `gh-organvm-object-lessons-19-605a` | `clean+merged+idle` | no |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `clean+merged+idle` | no |
| `resolve-organvm-i-theoria-.github-459-1ade` | `owner-blocker` | no |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `remote-merged` | no |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | `documented-residue` | no |

The older scan notes below are retained as lineage for how these roots were classified and
preserved during the 2026-06-27 cleanup pass.

Evidence commands:

- `python3 scripts/worktree-debt.py --json`: 14 roots, 8 debt-bearing roots after five
  duplicate PR-preserved local worktrees were removed from `.limen-worktrees`.
- per-root `git status --porcelain`, `git log --oneline -5`, `git cherry <default> HEAD`.
- non-Git residue inspection with `find` and direct reads of cache metadata files.

Older cleanup-pass classes retained for lineage:

- 2 dirty working trees counted as debt.
- 3 local unpushed or remote-mismatched commit roots.
- 2 non-Git residue roots.
- 4 active roots inside the idle grace window.
- 1 clean root not merged to default, with a draft PR receipt.
- 2 clean, merged, idle roots.
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
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror` | merged PR preserved | branch `limen/bld-mirror-mirror-harden-350f`; likely hardening task; no exact task slug in board | clean; PR [#67](https://github.com/organvm/mirror-mirror/pull/67) is `MERGED`; live `headRefOid` `f44da8e936d6d77fe9869c433372a697408f8491` equals local HEAD; CI `Lint, build & test` passed before merge; exact merged receipt recorded in `docs/worktree-preservation-receipts.json` | remote-merged receipt; no local source debt remains | Reclaim the local checkout only after normal operator acceptance; no code PR remains to merge. |
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | open PR remote-preserved | branch `limen/bld-my--father-mother-harden-44b2`; likely hardening task; no exact task slug in board | local HEAD `ff5d36d` exactly equals PR #28 `headRefOid`; draft PR [#28](https://github.com/organvm/my--father-mother/pull/28); local predicate passed `python3 -m py_compile main.py` and `python3 -m pytest -q` (99 passed); GitHub merge state `UNSTABLE`; one lint check is failing | remote-pr-open receipt; no local-only source preservation remains | Fix/retest PR #28 or supersede by a named branch that preserves the request-validation and structured-logging hardening. Reclaim local checkout only after operator acceptance. |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | open PR remote-preserved | branch `limen/bld-promptscope-next-rev-3fde`; likely next-revenue task; no exact task slug in board | local HEAD `362ec18` exactly equals PR #15 `headRefOid`; draft PR [#15](https://github.com/organvm/promptscope/pull/15); local source checks passed `node --check public/app.js`, TypeScript source check with `--skipLibCheck`, and `git diff --check`; declared `npm run typecheck` is blocked by existing `@cloudflare/workers-types` / `lib.webworker` declaration conflicts; GitHub merge state `DIRTY` | remote-pr-open receipt; no local-only source preservation remains | Rebase/retest PR #15 or supersede by a named branch that preserves the account dashboard and `/api/account` surface. Reclaim local checkout only after operator acceptance. |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation` | local checkout removed; draft PR open | branch `limen/bld-universal-mail--automation-readme-9031`; likely README task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `29f6b4b`; PR [#108](https://github.com/organvm/universal-mail--automation/pull/108); README marker check passed; `python3 cli.py -h` passed; `python3 -m py_compile cli.py api/app.py api/plans.py mcp_server/server.py` passed; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_config.py tests/test_models.py tests/test_rules.py tests/test_web.py` passed 158 tests | remote PR preserved; no local debt root remains | Review README modernization and merge, or supersede by a named successor that preserves this content. Recreate a local worktree from the branch only if needed. |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter` | local checkout removed; draft PR open | branch `limen/bld2-a-i-chat--exporter-integration-tests-a00b`; likely integration-tests task; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `d0d633c`; PR [#96](https://github.com/organvm/a-i-chat--exporter/pull/96); commits `6d73e1a`, `d0d633c`; `pnpm test` passed; `pnpm lint` passed with warnings; branch was 32 behind `origin/master` at preservation time | remote PR preserved; no local debt root remains | Review freshness/CI, then merge or name a successor PR that absorbed both commits. Recreate a local worktree from the branch only if needed. |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine` | open PR remote-preserved | branch `limen/cifix-organvm-i-theoria-conversation-corpus-engine-f02e`; likely CI-fix task; no exact task slug in board | local HEAD `0f96c88` exactly equals PR #60 `headRefOid`; draft PR [#60](https://github.com/organvm/conversation-corpus-engine/pull/60); local checks passed: `python3 -m pip install -e ".[dev]"`, `python3 -m pytest tests/ -v --tb=short` (351 passed), `python3 -m ruff check src/ tests/`, `python3 -m ruff format --check src/ tests/`, schema import command; 2026-06-28 live receipt shows GitHub CI and CodeQL all passed with merge state `CLEAN` | remote-pr-open receipt; no local-only source preservation remains | Review and merge PR #60, or supersede by named branch/PR. Reclaim local checkout only after operator acceptance. |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | remote-superseded dirty local checkout | branch `limen/cifix-organvm-i-theoria-hierarchia-mundi-3145`; likely CI/test task; no exact task slug in board | HEAD `677df2b`; local draft is behind `origin/main` by 6; dirty tracked files only reorder imports or remove unused imports; untracked `tests/test_smoke.py` is covered by current `origin/main`, which also includes broader `tests/test_loader.py` and `tests/test_cli.py`; scanner reason is now `remote-superseded` via `docs/worktree-preservation-receipts.json` | remote/default supersession receipt; no PR needed; not lifecycle debt | Reclaim only after normal operator acceptance; do not dispatch this stale root as unique work. |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles` | open PR remote-preserved | branch `limen/discover-organvm-kerygma-profiles-6c74`; discovery task; no exact task slug in board | local HEAD `d7fd19e` exactly equals PR #8 `headRefOid`; draft PR [#8](https://github.com/organvm/kerygma-profiles/pull/8); generated files remain on disk but are ignored; `python3 -m pytest` passed 24 tests; `python3 -m ruff check .` passed; 2026-06-28 live CI `test` check passed and merge state is `CLEAN` | remote-pr-open receipt; no local-only source preservation remains | Review and merge the generated-artifact hygiene PR, or supersede by a named successor. Reclaim local checkout only after operator acceptance. |
| `exporter-mp` | `organvm/a-i-chat--exporter` | local checkout removed; draft PR open | branch `limen/exporter-multiprovider`; explicit multiprovider branch; no exact task slug in board | clean before removal; local `HEAD` matched fetched PR head `dd73cce`; PR [#95](https://github.com/organvm/a-i-chat--exporter/pull/95); commits `5c3298b`, `6c88427`, `dd73cce`; `pnpm test` passed; `pnpm lint` passed with warnings after lint-setup compatibility fix | remote PR preserved; no local debt root remains | Review provider behavior and CI, then merge or supersede by named branch/PR. Recreate a local worktree from the branch only if needed. |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | documented generated-results residue; private patch preserved | branch `limen/gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38`; generated CI-green task; no exact task slug in board | HEAD `80e7617`; checkout is at `origin/main`; only local deltas are 11 tracked `structure-tests/results/ex01` through `ex11` JSON snapshots; exact generated-results patch preserved in `docs/worktree-preservation-receipts.json` with SHA-256 `92dc514490c7bbf3c6a14eb3889656563d070a23af55af3d64f2a16999d63bc9`; repo README says no live URL, installable package, runnable release, or documented execution path | documented non-source residue; do not PR or delegate this patch | Reclaim only after operator acceptance. If Sovereign becomes active again, regenerate current structure-test snapshots from a fresh owner packet rather than using this stale generated-results patch. |
| `gen-organvm-mirror-mirror-security-0622-c552` | `organvm/mirror-mirror` | reclaimed, content-preserved | branch `limen/gen-organvm-mirror-mirror-security-0622-c552`; generated security task; no exact task slug in board | prior evidence: clean HEAD `afed90a`; `git cherry origin/main HEAD` patch-equivalent (`- afed90a...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value on default branch. |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | unknown | non-Git residue | root slug says generated CI-green for `the-invisible-ledger`; no git metadata or exact board slug | contains only empty `dist/` directory; no files; receipt in `docs/worktree-preservation-receipts.json` | documented non-source residue | No unique artifact to preserve. Reclaimable only after operator acceptance; no deletion in this pass. |
| `gen-organvm-the-invisible-ledger-security-0622-d8f8` | `organvm/the-invisible-ledger` | reclaimed, content-preserved | branch `limen/sec-audit-0622`; generated security task; merged as PR #30 per prior audit | prior evidence: clean HEAD `b208078`; `git cherry origin/main HEAD` patch-equivalent (`- b208078...`); background reaper log `2026-06-27T13:05:49Z` removed this root | lifecycle closed; no unique source was local-only | No action unless a later audit finds missing value beyond merged PR #30. |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | dirty, high risk; private patch preserved | branch `limen/gen-organvm-universal-mail--automation-test-coverage-0625-151e`; generated test-coverage task; no exact task slug in board | HEAD `bff9ae1`; 167 tracked deletions including docs, package files, source, workflows; ahead 0/behind 17; `HEAD` is an ancestor of `origin/main` `5ca2baf`; no remote branch and no PR for this exact branch; no sparse checkout; skip-worktree count 0; private preservation receipt `docs/worktree-preservation-receipts.json` records patch SHA-256 `01f1705aaa210e3c42944f228e371e6d81547fd8ab93becd6ce701ce9a126760`; untracked material classified as generated `.venv`/`__pycache__` residue | stale broken checkout/deletion artifact; do not PR or delegate this patch | Reclaim only after operator acceptance. If Universal Mail Automation owner work is needed, recreate from `origin/main` or a current named PR branch, not this deletion root. |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons` | PR closed; default branch preserves local head | branch `limen/gh-organvm-object-lessons-19-605a`; GitHub issue/root slug; no exact task slug in board | branch force-with-lease updated to `745a1ba`, matching current `origin/main`; PR [#22](https://github.com/organvm/object-lessons/pull/22) is `CLOSED`; live PR head/base OIDs, local HEAD, and `origin/main` all equal `745a1baa57874b4e819a0eba4b983246f72e5539`; original Letterboxd ingestion payload is already on default via PR #20; package-lock-only follow-up was patch-equivalent upstream; `git cherry origin/main HEAD` produced no unique commits; `git diff --check origin/main..HEAD` passed | remote-default-proof receipt; no local source debt remains | Reclaim the local checkout only after normal operator acceptance; no code PR remains to merge. |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | `organvm/the-invisible-ledger` | default branch preserves local head | branch `limen/resolve-a-organvm-the-invisible-ledger-4-f657`; issue resolution task | local HEAD and `origin/main` both equal `2e785e4ad2976ea8018c27af3e6108fe09a79a95`; `git cherry origin/main HEAD` and `git diff --check origin/main..HEAD` are empty; no GitHub PR or remote head exists for this task branch; old local PostgreSQL adapter tip is still preserved as `preserve/resolve-a-organvm-the-invisible-ledger-4-f657-1741370` at `1741370e59110aa3f667b9d0f48ede43277eb6a5` | remote-default-proof receipt; no local source debt remains | Reclaim the local checkout only after normal operator acceptance; open no duplicate PR unless audit finds missing value beyond landed adapter/billing work. |
| `resolve-organvm-i-theoria-.github-459-1ade` | `organvm/.github` | stale divergent automation patch; private patch preserved | branch `limen/resolve-organvm-i-theoria-.github-459-1ade`; organization issue resolution task; no exact task slug in board | local commit `0035dff`; exact patch preserved in `docs/worktree-preservation-receipts.json` with SHA-256 `020b4c9e8227d560caa10714aac24376e56dea272de3563af7211b4d3b0f4a25`; branch is ahead 10 and behind 43 against `origin/main`; no PR exists for this head branch; HEAD patch touches `.github/workflows/gemini-review.yml`, `.github/workflows/version-control-standards.yml`, dashboard TS shim files, and `tsconfig.json`, while current default only has `ci-minimal`, `dependabot-auto-merge`, `dispatch-receiver`, and `stale` workflows | owner blocker; do not dispatch as a normal PR branch | Do not open a direct PR from this divergent branch. If the idea is still needed, create a new narrow owner packet that cherry-picks only the Limen automation branch-policy rule into the current `organvm/.github` default tree. |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper` | merged PR preserved | branch `limen/rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f`; revenue-readiness task; no exact task slug in board | PR [#328](https://github.com/organvm/public-record-data-scrapper/pull/328) is `MERGED`; live `headRefOid` `3af406915ec3a3c67f0843f963cb6a3658bcc9d9` equals local HEAD; checks `gate`, `Secret Pattern Detection`, and `validate-dependencies` passed before merge; exact merged receipt recorded in `docs/worktree-preservation-receipts.json` | remote-merged receipt; no local source debt remains | Reclaim the local checkout only after normal operator acceptance; no code PR remains to merge. |
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
  That did not lose unique source. On 2026-06-29 the operator policy was tightened in the
  other direction: `scripts/drain.sh` now defaults `LIMEN_RECLAIM_APPLY=1`, but the reaper
  still refuses dirty, unique-unpushed, unmerged, active, or live/self roots.
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
- Object Lessons PR #22 is no longer remote-close debt: the branch is patch-equivalent
  to default after PR #20, and GitHub closed #22 after the no-diff branch update.
- Public Record Data Scraper PR #328 was rebased onto current `origin/main`, its
  OpenAPI conflict was resolved by preserving the API-key/readiness surface plus the
  UCC response schema, and all GitHub checks passed.

## Drain Order

1. Close the two non-Git residue roots by keeping this classification visible; remove
   only after a scripted reclaim gate records the classification or the operator explicitly
   accepts that residue cleanup.
2. Drive the remaining open draft PR receipts to merge or named supersession:
   [domus-genoma#144](https://github.com/organvm/domus-genoma/pull/144),
   [mirror-mirror#67](https://github.com/organvm/mirror-mirror/pull/67),
   [conversation-corpus-engine#60](https://github.com/organvm/conversation-corpus-engine/pull/60),
   [a-i-chat--exporter#96](https://github.com/organvm/a-i-chat--exporter/pull/96),
   [a-i-chat--exporter#95](https://github.com/organvm/a-i-chat--exporter/pull/95),
   [public-record-data-scrapper#328](https://github.com/organvm/public-record-data-scrapper/pull/328),
   [kerygma-profiles#8](https://github.com/organvm/kerygma-profiles/pull/8), and
   [universal-mail--automation#108](https://github.com/organvm/universal-mail--automation/pull/108),
   plus [media-ark#50](https://github.com/organvm/media-ark/pull/50). PR
   [object-lessons#22](https://github.com/organvm/object-lessons/pull/22) is closed
   as a named default-branch supersession.
3. Work the dirty roots from lowest risk to highest risk: generated-only caches,
   remaining single-file deltas, multi-file implementation deltas, then the broad deletion root.
4. Keep the historical content-preserved reclaims visible as receipts; do not
   perform further local removals unless the target has exact remote/default
   preservation or explicit operator acceptance.
