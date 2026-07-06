# Session Attack Paths

Generated: `2026-07-06T15:42:57+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `15291` files, `131758` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `7`.
- Worktree preservation receipts: `89`.
- Parked blockers: `8`.
- Local lifecycle footprint: `33.3 GiB`.
- Candidate lanes: `blocker` 4, `family` 7, `human-gate` 17, `observe` 110, `owner-blocker` 7, `parked` 5, `preserve` 4, `remote-close` 2, `remote-pr-open` 12, `remote-proof` 10.

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
| 1 | `heal-cifix-organvm-organvm-engine-139-9dbf53bf` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 2 | `heal-cifix-organvm-organvm-engine-144-0ef4c596` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 3 | `heal-cifix-organvm-organvm-engine-144-e2096564` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 4 | `heal-cifix-organvm-organvm-ontologia-11-55899198` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 5 | `worktree-lifecycle-debt` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve or owner-record each root; no deletion of unique work. |
| 6 | `worktree-remote-branches-missing` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| 7 | `worktree_lifecycle` | `family` | `family` | 67 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 8 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 9 | `heal-rebase-4444j99-hokage-chess-89-0448f70e` | `worktree` | `remote-proof` | 64 | reason `not-merged-to-default`; prompts 3; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 10 | `heal-cifix-organvm-limen-423-47a6f9ec` | `worktree` | `observe` | 62 | reason `active(<6h)`; prompts 126; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 11 | `heal-cifix-organvm-organvm-ontologia-11-a86cf99f` | `worktree` | `remote-proof` | 60 | reason `clean+merged+idle`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 12 | `heal-cifix-organvm-organvm-ontologia-12-2c2c85ba` | `worktree` | `remote-proof` | 60 | reason `clean+merged+idle`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 13 | `heal-cifix-organvm-organvm-ontologia-13-953633bb` | `worktree` | `remote-proof` | 60 | reason `clean+merged+idle`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 14 | `org-financial-organ-face-0704-5a117787` | `worktree` | `remote-proof` | 60 | reason `clean+merged+idle`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 15 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 16 | `heal-cifix-organvm-a-i--skills-27-d0df3765` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 17 | `heal-cifix-organvm-a-i--skills-27-f0edd746` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 18 | `heal-cifix-organvm-a-i--skills-27-f7577686` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 19 | `heal-cifix-organvm-a-i--skills-28-d93d775c` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 20 | `heal-cifix-organvm-a-i-chat--exporter-49-1992eb0d` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 21 | `heal-cifix-organvm-a-i-chat--exporter-54-3049e7fb` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 22 | `heal-cifix-organvm-limen-421-8f14068b` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 23 | `heal-cifix-organvm-limen-422-eda116ed` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 24 | `heal-cifix-organvm-limen-424-8db5dab0` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 25 | `heal-cifix-organvm-limen-425-164d86db` | `worktree` | `observe` | 50 | reason `active(<6h)`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |

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
