# Session Attack Paths

Generated: `2026-07-04T19:17:17+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `14911` files, `128730` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `0`.
- Worktree preservation receipts: `77`.
- Parked blockers: `6`.
- Local lifecycle footprint: `29.7 GiB`.
- Candidate lanes: `family` 7, `human-gate` 51, `observe` 5, `owner-blocker` 6, `parked` 5, `remote-close` 1, `remote-pr-open` 10, `remote-proof` 6.

## Ordering Model

- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.
- Network/environment substrate failures outrank ordinary repo cleanup because they can make every agent misclassify auth, dispatch, and GitHub symptoms.
- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.
- Worktree receipts that require operator acceptance before reclaim are human-gated, not autonomous lane work.
- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.
- Then: repeated lifecycle/family loops that need owner packets before delegation.
- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.

## Ranked Paths

| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |
|---:|---|---|---|---:|---|---|---|
| 1 | `heal+jules-revive-census-converge` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 988; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `iterative-coalescing-wilkinson` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 234; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 3 | `partitioned-beaming-cosmos` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 754; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 4 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 5 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 6 | `polymorphic-popping-phoenix` | `worktree` | `remote-proof` | 58 | reason `active(<24h)`; prompts 329; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 7 | `ticklish-bubbling-robin` | `worktree` | `remote-proof` | 58 | reason `active(<24h)`; prompts 2085; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 8 | `worktree_lifecycle` | `family` | `family` | 57 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 9 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 10 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 11 | `agent_coordination` | `family` | `family` | 40 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 12 | `linear-conjuring-bear` | `worktree` | `remote-close` | 40 | reason `active(<24h)`; prompts 2136; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 13 | `peer-audited--behavioral-blockchain` | `worktree` | `owner-blocker` | 35 | reason `owner-blocker`; prompts 650; remote `missing`; open PRs 0; receipt `private_patch_preserved` | codex first; opencode/jules after packetization | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 14 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 15 | `technical_debt_ci` | `family` | `family` | 34 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 16 | `feat-gcp-sa-organ` | `worktree` | `owner-blocker` | 34 | reason `owner-blocker`; prompts 727; remote `missing`; open PRs 0; receipt `owner_commit_needs_packet` | codex first; opencode/jules after packetization | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 17 | `agent-code-review-0704-113` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 18 | `fable-adjudication-followup-0704` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 19 | `unpark-live-checkout` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 20 | `convergence_corpus` | `family` | `family` | 26 | sessions 10; states CLOSED 10; prompts 37 | codex | Promote durable atoms through session-meta and knowledge-corpus. |
| 21 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `human-gate` | 26 | reason `owner-blocker`; prompts 100; remote `missing`; open PRs 0; receipt `private_patch_preserved` | human/codex-prep | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 22 | `heal-cifix-organvm-limen-449-25ce` | `worktree` | `human-gate` | 21 | reason `documented-residue`; prompts 3; remote `not-a-git-dir`; open PRs 0; receipt `documented_non_source_residue` | human/codex-prep | No unique source to preserve; directory is not a Git checkout and contains only stale lifecycle-pressure logs. Reclaim only after normal operator acceptance; no deletion in this pass. |
| 23 | `heal-cifix-organvm-limen-450-ed38` | `worktree` | `human-gate` | 21 | reason `documented-residue`; prompts 3; remote `not-a-git-dir`; open PRs 0; receipt `documented_non_source_residue` | human/codex-prep | No unique source to preserve; directory is not a Git checkout and contains only stale lifecycle-pressure logs. Reclaim only after normal operator acceptance; no deletion in this pass. |
| 24 | `heal-cifix-organvm-limen-450-fc3a` | `worktree` | `human-gate` | 21 | reason `documented-residue`; prompts 3; remote `not-a-git-dir`; open PRs 0; receipt `documented_non_source_residue` | human/codex-prep | No unique source to preserve; directory is not a Git checkout and contains only stale lifecycle-pressure logs. Reclaim only after normal operator acceptance; no deletion in this pass. |
| 25 | `heal-cifix-organvm-limen-451-0b29` | `worktree` | `human-gate` | 21 | reason `documented-residue`; prompts 3; remote `not-a-git-dir`; open PRs 0; receipt `documented_non_source_residue` | human/codex-prep | No unique source to preserve; directory is not a Git checkout and contains only stale lifecycle-pressure logs. Reclaim only after normal operator acceptance; no deletion in this pass. |

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
