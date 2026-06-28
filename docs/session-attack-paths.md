# Session Attack Paths

Generated: `2026-06-28T00:40:53+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9484` files, `92698` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `11`.
- Parked blockers: `10`.
- Local lifecycle footprint: `4.9 GiB`.
- Candidate lanes: `blocker` 7, `drain` 1, `family` 7, `observe` 2, `parked` 3, `preserve` 6, `remote-close` 3, `remote-proof` 1, `residue` 2.

## Ordering Model

- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.
- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.
- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.
- Then: repeated lifecycle/family loops that need owner packets before delegation.
- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.

## Ranked Paths

| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |
|---:|---|---|---|---:|---|---|---|
| 1 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `preserve` | 94 | reason `dirty`; prompts 100; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 2 | `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `worktree` | `preserve` | 85 | reason `dirty`; prompts 71; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 3 | `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | `worktree` | `residue` | 83 | reason `not-a-git-dir`; prompts 94; remote `not-a-git-dir`; open PRs 0 | codex first; opencode/jules after packetization | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 4 | `bld-my--father-mother-harden-44b2` | `worktree` | `preserve` | 78 | reason `dirty`; prompts 5; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 5 | `bld-promptscope-next-rev-3fde` | `worktree` | `preserve` | 78 | reason `dirty`; prompts 4; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 6 | `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `worktree` | `preserve` | 78 | reason `dirty`; prompts 3; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 7 | `local-lifecycle-disk-pressure` | `blocker` | `drain` | 74 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 8 | `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | `worktree` | `residue` | 74 | reason `not-a-git-dir`; prompts 4; remote `not-a-git-dir`; open PRs 0 | codex first; opencode/jules after packetization | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 9 | `worktree_lifecycle` | `family` | `family` | 73 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 10 | `remote-task-pr-receipt-errors` | `blocker` | `blocker` | 72 | category `remote_receipt`; status `needs_refresh` | codex | Rerun or repair access separately before treating those PR refs as closure evidence. |

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
