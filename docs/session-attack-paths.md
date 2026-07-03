# Session Attack Paths

Generated: `2026-07-03T06:25:05+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9711` files, `98045` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `0`.
- Worktree preservation receipts: `33`.
- Parked blockers: `6`.
- Local lifecycle footprint: `21.6 GiB`.
- Candidate lanes: `family` 7, `human-gate` 14, `owner-blocker` 2, `parked` 5, `remote-pr-open` 10, `remote-proof` 7.

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
| 1 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 2 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 3 | `worktree_lifecycle` | `family` | `family` | 57 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 4 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 5 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 6 | `agent_coordination` | `family` | `family` | 40 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 7 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 8 | `technical_debt_ci` | `family` | `family` | 34 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 9 | `the-invisible-ledger` | `worktree` | `remote-pr-open` | 29 | reason `remote-pr-open`; prompts 2919; remote `missing`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |
| 10 | `GEN-organvm-limen-ci-green-0702` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 11 | `feat+cvstos-vvltvs-organs` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 12 | `feat+workstream-channels` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 13 | `feat-codex-skill-slim` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 14 | `feat-tabularius-record-keeper` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 15 | `linear-conjuring-bear` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 16 | `ticklish-bubbling-robin` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 17 | `convergence_corpus` | `family` | `family` | 26 | sessions 10; states CLOSED 10; prompts 37 | codex | Promote durable atoms through session-meta and knowledge-corpus. |
| 18 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `human-gate` | 26 | reason `owner-blocker`; prompts 100; remote `missing`; open PRs 0; receipt `private_patch_preserved` | human/codex-prep | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 19 | `cloud-runtime-endpoint-unconfigured` | `blocker` | `parked` | 18 | category `cloud_runtime`; status `parked` | codex | Keep separate from session intake; configure/probe runtime only in a deploy/runtime task. |
| 20 | `uncategorized` | `family` | `family` | 18 | sessions 2; states STALLED 2; prompts 10 | codex | Inspect privately and add classifier/owner route. |
| 21 | `triptych-story` | `worktree` | `remote-pr-open` | 17 | reason `remote-pr-open`; prompts 212; remote `present`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #1, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 22 | `maddie-boundary-20260629` | `worktree` | `remote-pr-open` | 11 | reason `remote-pr-open`; prompts 68; remote `present`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #11, then merge, supersede, or archive the Maddie boundary evidence branch. Local checkout is no longer the only review surface. |
| 23 | `student-email-d2l-support-20260629` | `worktree` | `remote-pr-open` | 11 | reason `remote-pr-open`; prompts 67; remote `present`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #12, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 24 | `limen-network-substrate-20260628` | `worktree` | `remote-pr-open` | 7 | reason `remote-pr-open`; prompts 21; remote `present`; open PRs 0; receipt `open_pr_preserved` | codex first; opencode/jules after packetization | Review draft PR #494, then merge, supersede, or archive the network substrate healing branch. Local checkout is no longer the only review surface. |
| 25 | `cloud-credential-handles-unconfigured` | `blocker` | `parked` | 6 | category `auth_credentials`; status `parked` | human/codex-prep | Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it. |

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
