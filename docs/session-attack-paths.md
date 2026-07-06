# Session Attack Paths

Generated: `2026-07-06T09:27:57+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `15221` files, `131016` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `0`.
- Worktree preservation receipts: `80`.
- Parked blockers: `7`.
- Local lifecycle footprint: `26.1 GiB`.
- Candidate lanes: `blocker` 1, `family` 7, `human-gate` 11, `observe` 18, `owner-blocker` 6, `parked` 5, `remote-close` 1, `remote-pr-open` 12, `remote-proof` 1, `residue` 2.

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
| 1 | `fluttering-twirling-abelson` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 315; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 3 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 4 | `worktree_lifecycle` | `family` | `family` | 57 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 5 | `org-health-organ-firstslice-0704-aac2b482` | `worktree` | `residue` | 56 | reason `generated-log-shell`; prompts 3; remote `not-a-git-dir`; open PRs 0 | codex first; opencode/jules after packetization | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 6 | `org-health-organ-firstslice-0704-caa4e142` | `worktree` | `residue` | 56 | reason `generated-log-shell`; prompts 3; remote `not-a-git-dir`; open PRs 0 | codex first; opencode/jules after packetization | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 7 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 8 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 9 | `heal-cifix-organvm-organvm-ontologia-11-a86cf99f` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 10 | `heal-cifix-organvm-organvm-ontologia-12-2c2c85ba` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 11 | `heal-cifix-organvm-organvm-ontologia-13-953633bb` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 12 | `heal-rebase-4444j99-hokage-chess-89-0448f70e` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 13 | `owner-state-dirty-session-meta` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 14 | `agent_coordination` | `family` | `family` | 40 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 15 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 16 | `technical_debt_ci` | `family` | `family` | 34 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 17 | `feat-gcp-sa-organ` | `worktree` | `owner-blocker` | 34 | reason `owner-blocker`; prompts 727; remote `missing`; open PRs 0; receipt `owner_commit_needs_packet` | codex first; opencode/jules after packetization | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 18 | `heal-cifix-organvm-organvm-engine-124-e0bb2d06` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 19 | `heal-cifix-organvm-organvm-engine-130-8a6060e4` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 20 | `heal-cifix-organvm-organvm-engine-139-9dbf53bf` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 21 | `heal-cifix-organvm-organvm-engine-143-a164221c` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 22 | `heal-cifix-organvm-organvm-engine-144-0ef4c596` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 23 | `heal-cifix-organvm-organvm-ontologia-10-64603ca7` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 24 | `heal-cifix-organvm-organvm-ontologia-11-55899198` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 25 | `limen_jules-org-health-organ-kernel-0630-0289` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |

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
