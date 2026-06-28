# Session Attack Paths

Generated: `2026-06-28T16:23:10+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9489` files, `92795` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `0`.
- Worktree preservation receipts: `12`.
- Parked blockers: `9`.
- Local lifecycle footprint: `5.3 GiB`.
- Candidate lanes: `blocker` 4, `documented-residue` 3, `family` 7, `human-gate` 2, `owner-blocker` 2, `parked` 4, `remote-merged` 2, `remote-pr-open` 4, `remote-proof` 2, `remote-superseded` 1.

## Ordering Model

- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.
- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.
- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.
- Then: repeated lifecycle/family loops that need owner packets before delegation.
- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.

## Ranked Paths

| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |
|---:|---|---|---|---:|---|---|---|
| 1 | `worktree_lifecycle` | `family` | `family` | 73 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 2 | `session_lifecycle` | `family` | `family` | 72 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 3 | `worktree-remote-branches-missing` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| 4 | `github_review` | `family` | `family` | 61 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 5 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 6 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 7 | `gh-organvm-object-lessons-19-605a` | `worktree` | `remote-proof` | 49 | reason `clean+merged+idle`; prompts 73; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 8 | `resolve-a-organvm-the-invisible-ledger-4-f657` | `worktree` | `remote-proof` | 48 | reason `clean+merged+idle`; prompts 5; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 9 | `agent_coordination` | `family` | `family` | 46 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 10 | `owner-state-dirty-knowledge-corpus` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 11 | `owner-state-dirty-session-meta` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 12 | `technical_debt_ci` | `family` | `family` | 40 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 13 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 14 | `convergence_corpus` | `family` | `family` | 32 | sessions 10; states CLOSED 10; prompts 37 | codex | Promote durable atoms through session-meta and knowledge-corpus. |
| 15 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `owner-blocker` | 32 | reason `owner-blocker`; prompts 100; remote `missing`; open PRs 0; receipt `private_patch_preserved` | codex first; opencode/jules after packetization | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 16 | `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | `worktree` | `documented-residue` | 24 | reason `documented-residue`; prompts 94; remote `not-a-git-dir`; open PRs 0; receipt `cache_only_residue` | codex first; opencode/jules after packetization | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 17 | `cloud-runtime-endpoint-unconfigured` | `blocker` | `blocker` | 18 | category `cloud_runtime`; status `parked` | codex | Keep separate from session intake; configure/probe runtime only in a deploy/runtime task. |
| 18 | `uncategorized` | `family` | `family` | 18 | sessions 2; states STALLED 2; prompts 10 | codex | Inspect privately and add classifier/owner route. |
| 19 | `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `worktree` | `remote-superseded` | 18 | reason `remote-superseded`; prompts 71; remote `missing`; open PRs 0; receipt `superseded_on_origin_main` | codex first; opencode/jules after packetization | No PR needed; local dirty smoke-test/root-fix draft is superseded by origin/main, including tests/test_smoke.py plus broader loader and CLI coverage. Reclaim only after normal operator acceptance. |
| 20 | `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | `worktree` | `documented-residue` | 15 | reason `documented-residue`; prompts 4; remote `not-a-git-dir`; open PRs 0; receipt `empty_generated_residue` | codex first; opencode/jules after packetization | No unique source to preserve; directory contains only an empty dist/ directory. Reclaim only after normal operator acceptance. |
| 21 | `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `worktree` | `documented-residue` | 11 | reason `documented-residue`; prompts 3; remote `missing`; open PRs 0; receipt `documented_non_source_residue` | codex first; opencode/jules after packetization | Do not PR or delegate this generated-results patch. The checkout is at origin/main, the only local deltas are 11 tracked structure-tests/results/*.json snapshots, the repo README classifies the project as a parked docs-only shell with no runnable release path, and the exact patch is privately preserved. Reclaim only after operator acceptance; regenerate current structure-test snapshots from a fresh owner packet if this repo becomes active again. |
| 22 | `cloud-credential-handles-unconfigured` | `blocker` | `parked` | 6 | category `auth_credentials`; status `parked` | human/codex-prep | Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it. |
| 23 | `credential-codex-auth-sessions` | `blocker` | `parked` | 6 | category `auth_credentials`; status `parked` | human/codex-prep | Keep parked unless a future scoped task explicitly requires the account action. |
| 24 | `auth_credentials` | `family` | `parked` | -1 | sessions 405; states ALIVE 1, CLOSED 364, PARKED 40; prompts 2491 | human/codex-prep | Keep hung as credential workstream; prepare only non-secret prerequisites. |
| 25 | `resolve-organvm-i-theoria-.github-459-1ade` | `worktree` | `owner-blocker` | -1 | reason `owner-blocker`; prompts 5; remote `unknown`; open PRs 0; receipt `history_mismatch_patch_preserved` | codex first; opencode/jules after packetization | Do not open a direct PR from this branch. The branch is ahead 10 and behind 43 against origin/main, has no open/closed PR, and its HEAD patch targets .github/workflows/gemini-review.yml, .github/workflows/version-control-standards.yml, dashboard TS shim files, and tsconfig.json, while current origin/main only has ci-minimal, dependabot-auto-merge, dispatch-receiver, and stale workflows. Preserve as private patch evidence; if needed, create a new narrow owner packet to cherry-pick only the Limen automation branch-policy idea into the current organvm/.github default tree. |

## Delegation Gate

- A path may be assigned only when it has an owner repo or owner ledger, a bounded next action, no raw-secret dependency, and a verification predicate or blocker receipt.
- Claude is a context source while near limit; it should not be the default executor.
- Jules/OpenCode/Agy get packets only after the ranked path is narrowed to a repo, branch, predicate, and expected receipt.
- Gemini stays parked if auth is not already repaired.

## Private Output

- Private attack-path index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/session-attack-paths.json`.
- The private index keeps structured path evidence from redacted indexes; it contains no raw prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-blockers-ledger.py --write`
- Refresh attack paths: `python3 scripts/session-attack-paths.py --write`
- Refresh the current conductor tranche: `python3 scripts/conductor-tranche.py --write`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
