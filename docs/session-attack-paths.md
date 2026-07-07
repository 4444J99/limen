# Session Attack Paths

Generated: `2026-07-07T00:19:44+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `15590` files, `136694` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `70`.
- Worktree preservation receipts: `89`.
- Parked blockers: `8`.
- Local lifecycle footprint: `39.7 GiB`.
- Candidate lanes: `blocker` 3, `drain` 1, `family` 7, `human-gate` 18, `observe` 293, `owner-blocker` 7, `parked` 4, `preserve` 42, `remote-close` 12, `remote-pr-open` 12, `remote-proof` 151.

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
| 1 | `heal-cifix-organvm-limen-424-8db5dab0` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 2 | `heal-cifix-organvm-limen-428-4b320e87` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 3 | `heal-cifix-organvm-limen-430-7c7129d9` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 4 | `heal-cifix-organvm-limen-438-da3b854e` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 5 | `heal-cifix-organvm-limen-444-a00aa985` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 6 | `heal-cifix-organvm-public-process-30-59ffa133` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 7 | `heal-rebase-organvm-a-i-chat--exporter-31-78a6445b` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 8 | `heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 9 | `org-financial-organ-face-0704-bd436529` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 10 | `org-governance-organ-selffeed-0703-00694775` | `worktree` | `preserve` | 90 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 11 | `heal-cifix-organvm-limen-422-6b0c8ca2` | `worktree` | `preserve` | 78 | reason `dirty`; prompts 4; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 12 | `heal-cifix-organvm-limen-430-b979134a` | `worktree` | `remote-proof` | 76 | reason `not-merged-to-default`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 13 | `local-lifecycle-disk-pressure` | `blocker` | `drain` | 74 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 14 | `gh-4444j99-hokage-chess-39-25daa3dd` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 15 | `gh-4444j99-hokage-chess-39-c15d2ce9` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 16 | `heal-cifix-organvm-a-i--skills-27-7d6c0216` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 17 | `heal-cifix-organvm-a-i--skills-27-7ed7339a` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 18 | `heal-cifix-organvm-a-i--skills-27-8f4677cb` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 19 | `heal-cifix-organvm-limen-422-3c1a44a2` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 20 | `heal-cifix-organvm-limen-423-354fa844` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 21 | `heal-cifix-organvm-limen-423-40984048` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 22 | `heal-cifix-organvm-limen-423-e48b35df` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 23 | `heal-cifix-organvm-limen-429-4471ceb2` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 24 | `heal-cifix-organvm-limen-434-b6e642da` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 25 | `heal-cifix-organvm-limen-435-401dee02` | `worktree` | `preserve` | 72 | reason `dirty`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |

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
