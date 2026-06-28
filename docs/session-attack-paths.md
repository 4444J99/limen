# Session Attack Paths

Generated: `2026-06-28T15:34:57+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9489` files, `92795` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `8`.
- Worktree preservation receipts: `6`.
- Parked blockers: `8`.
- Local lifecycle footprint: `5.3 GiB`.
- Candidate lanes: `blocker` 5, `documented-residue` 3, `drain` 1, `family` 7, `owner-blocker` 2, `parked` 3, `remote-close` 6, `remote-proof` 2, `remote-superseded` 1.

## Ordering Model

- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.
- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.
- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.
- Then: repeated lifecycle/family loops that need owner packets before delegation.
- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.

## Ranked Paths

| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |
|---:|---|---|---|---:|---|---|---|
| 1 | `local-lifecycle-disk-pressure` | `blocker` | `drain` | 74 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 2 | `worktree_lifecycle` | `family` | `family` | 73 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 3 | `session_lifecycle` | `family` | `family` | 72 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 4 | `worktree-lifecycle-debt` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve or owner-record each root; no deletion of unique work. |
| 5 | `worktree-remote-branches-missing` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| 6 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `owner-blocker` | 64 | reason `dirty`; prompts 100; remote `missing`; open PRs 0; receipt `private_patch_preserved` | codex first; opencode/jules after packetization | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 7 | `github_review` | `family` | `family` | 61 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 8 | `gh-organvm-object-lessons-19-605a` | `worktree` | `remote-proof` | 49 | reason `clean+merged+idle`; prompts 73; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 9 | `resolve-a-organvm-the-invisible-ledger-4-f657` | `worktree` | `remote-proof` | 48 | reason `clean+merged+idle`; prompts 5; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 10 | `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `worktree` | `remote-close` | 47 | reason `not-merged-to-default`; prompts 79; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 11 | `agent_coordination` | `family` | `family` | 46 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 12 | `owner-state-dirty-knowledge-corpus` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 13 | `owner-state-dirty-session-meta` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 14 | `discover-organvm-kerygma-profiles-6c74` | `worktree` | `remote-close` | 42 | reason `not-merged-to-default`; prompts 24; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 15 | `technical_debt_ci` | `family` | `family` | 40 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 16 | `convergence_corpus` | `family` | `family` | 32 | sessions 10; states CLOSED 10; prompts 37 | codex | Promote durable atoms through session-meta and knowledge-corpus. |
| 17 | `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | `worktree` | `documented-residue` | 24 | reason `documented-residue`; prompts 94; remote `not-a-git-dir`; open PRs 0; receipt `cache_only_residue` | codex first; opencode/jules after packetization | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 18 | `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `worktree` | `remote-close` | 23 | reason `unpushed-commits`; prompts 79; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 19 | `cloud-runtime-endpoint-unconfigured` | `blocker` | `blocker` | 18 | category `cloud_runtime`; status `parked` | codex | Keep separate from session intake; configure/probe runtime only in a deploy/runtime task. |
| 20 | `uncategorized` | `family` | `family` | 18 | sessions 2; states STALLED 2; prompts 10 | codex | Inspect privately and add classifier/owner route. |
| 21 | `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `worktree` | `remote-superseded` | 18 | reason `remote-superseded`; prompts 71; remote `missing`; open PRs 0; receipt `superseded_on_origin_main` | codex first; opencode/jules after packetization | No PR needed; local dirty smoke-test/root-fix draft is superseded by origin/main, including tests/test_smoke.py plus broader loader and CLI coverage. Reclaim only after normal operator acceptance. |
| 22 | `bld-mirror-mirror-harden-350f` | `worktree` | `remote-close` | 16 | reason `unpushed-commits`; prompts 5; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 23 | `bld-my--father-mother-harden-44b2` | `worktree` | `remote-close` | 16 | reason `unpushed-commits`; prompts 5; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 24 | `bld-promptscope-next-rev-3fde` | `worktree` | `remote-close` | 16 | reason `unpushed-commits`; prompts 4; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 25 | `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | `worktree` | `documented-residue` | 15 | reason `documented-residue`; prompts 4; remote `not-a-git-dir`; open PRs 0; receipt `empty_generated_residue` | codex first; opencode/jules after packetization | No unique source to preserve; directory contains only an empty dist/ directory. Reclaim only after normal operator acceptance. |

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
