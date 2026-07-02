# Session Attack Paths

Generated: `2026-07-02T19:28:41+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9711` files, `98045` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `7`.
- Worktree preservation receipts: `24`.
- Parked blockers: `8`.
- Local lifecycle footprint: `21.1 GiB`.
- Candidate lanes: `blocker` 2, `family` 7, `human-gate` 8, `parked` 5, `remote-pr-open` 10, `remote-proof` 19, `residue` 1.

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
| 1 | `worktree-lifecycle-debt` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve or owner-record each root; no deletion of unique work. |
| 2 | `worktree-remote-branches-missing` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| 3 | `worktree_lifecycle` | `family` | `family` | 67 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 4 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 5 | `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | `worktree` | `residue` | 62 | reason `not-a-git-dir`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 6 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 7 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 8 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 9 | `agent_coordination` | `family` | `family` | 40 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 10 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 11 | `technical_debt_ci` | `family` | `family` | 34 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 12 | `the-invisible-ledger` | `worktree` | `remote-pr-open` | 29 | reason `remote-pr-open`; prompts 2919; remote `missing`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |
| 13 | `GEN-organvm-limen-ci-green-0702` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 14 | `feat+cvstos-vvltvs-organs` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 15 | `feat-clone-lifecycle-reap` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 16 | `feat-codex-skill-slim` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 17 | `feat-gcp-sa-organ` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 18 | `feat-materialize-fold` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 19 | `feat-tabularius-record-keeper` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 20 | `fix-wrangler-cred-one-spot` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 21 | `linear-conjuring-bear` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 22 | `parsed-finding-fern` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 23 | `pr-463` | `worktree` | `remote-proof` | 28 | reason `unpushed-commits`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 24 | `pr-466` | `worktree` | `remote-proof` | 28 | reason `unpushed-commits`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 25 | `pr-467` | `worktree` | `remote-proof` | 28 | reason `unpushed-commits`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |

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
