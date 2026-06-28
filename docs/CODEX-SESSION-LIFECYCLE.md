# Codex Session Lifecycle

Generated: `2026-06-27T21:42:32+00:00`
Horizon: `all local history`

## Canonical Decision

- Codex app/session history is lifecycle material, not disposable chat residue.
- Tracked output stays counts-only and route-oriented; raw prompts remain in local Codex stores and ignored private cartridge indexes.
- This classifier does not execute, delete, dispatch, push, merge, or solve credentials.
- Auth, login, key, token, password, and credential sessions are parked into the credential workstream unless directly scoped.

## State Summary

- Codex session files classified: `887`.
- Codex prompt history events indexed: `412` across `20` session ids.
- States: `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.

## Family Routes

| Family | Sessions | States | Prompt Events | Owner | Route |
|---|---:|---|---:|---|---|
| `auth_credentials` | 405 | `ALIVE` 1, `CLOSED` 364, `PARKED` 40 | 2491 | credential workstream | park unless a scoped task explicitly requires the account action |
| `session_lifecycle` | 159 | `CLOSED` 139, `STALLED` 20 | 636 | limen control plane | fold into session and prompt lifecycle ledgers |
| `github_review` | 158 | `CLOSED` 145, `STALLED` 13 | 615 | repo owner | map issue or PR to owner receipt before further review |
| `worktree_lifecycle` | 77 | `CLOSED` 62, `STALLED` 15 | 289 | worktree lifecycle | preserve branch or owner receipt before cleanup |
| `agent_coordination` | 40 | `CLOSED` 30, `STALLED` 10 | 133 | agent router | packetize only bounded, non-secret work for other agents |
| `technical_debt_ci` | 36 | `CLOSED` 33, `STALLED` 3 | 128 | repo predicate | run the narrow predicate and preserve failures as owner blockers |
| `convergence_corpus` | 10 | `CLOSED` 10 | 37 | corpus organs | route through session-meta, knowledge-corpus, and corpus-converge receipts |
| `uncategorized` | 2 | `STALLED` 2 | 10 | needs classifier | inspect privately, then add a family or owner receipt |

## Lifecycle Rules

- `ALIVE`: recently moving; do not interfere.
- `STALLED`: a user prompt appears newer than any recorded Codex task completion.
- `CLOSED`: Codex recorded task completion or no newer prompt is waiting.
- `PARKED`: credential/auth/login material; hung for a separate credential workstream.

## Commands

- Preview all history: `python3 scripts/codex-quicken.py --all`
- Write the digest, journal, and private index: `python3 scripts/codex-quicken.py --all --apply`
- Bounded preview: `python3 scripts/codex-quicken.py --days 14`
