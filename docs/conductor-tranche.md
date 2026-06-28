# Conductor Tranche

Generated: `2026-06-28T16:39:35+00:00`

Summary: `tranche-github-app-limen-bot-not-wired` -> `github-app-limen-bot-not-wired` (`human-gate`); stop before: Stop before creating/installing the GitHub App, calling `scripts/set-credential.sh`, writing any PEM/key material, or changing GitHub secrets without explicit human approval.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-github-app-limen-bot-not-wired` |
| Selected path | `github-app-limen-bot-not-wired` |
| Kind | `blocker` |
| Lane | `human-gate` |
| Score | `58` |
| Agent fit | `human/codex-prep` |
| Attack index generated | `2026-06-28T16:39:28+00:00` |
| Ranked paths read | `30` |
| Skipped family/parked/observe/auth paths | `session_lifecycle`, `worktree_lifecycle`, `github_review`, `agent_coordination`, `technical_debt_ci`, `local-lifecycle-disk-pressure`, `convergence_corpus`, `uncategorized`, `cloud-credential-handles-unconfigured`, `credential-codex-auth-sessions`, `auth_credentials` |

## Work Packet

Purpose: Clearly block limen[bot] until the GitHub App exists, is installed on `organvm`, and local/CI credentials are hydrated without exposing secret values.

Repo/worktree: `organvm/limen` conductor checkout only; GitHub App state is read-only.

Allowed files:

- `scripts/consolidation-gates.py`
- `scripts/gh-app-token.sh`
- `docs/github-app-architecture.md`
- `docs/consolidation/SCOPE-AND-APP.md`
- `docs/consolidation/GATES.md`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `.limen-private/session-corpus/lifecycle/consolidation-gates.json`

Forbidden:

- `/Users/4jp/Workspace/4444J99/portvs`
- `creative placement work`
- `plaintext secrets or credential values`
- `irreversible GitHub transfer/rename/App install/credential actions`
- `task-board mutation unless the direct request explicitly requires it`

Stop condition: Stop before creating/installing the GitHub App, calling `scripts/set-credential.sh`, writing any PEM/key material, or changing GitHub secrets without explicit human approval.

Receipt: docs/consolidation/GATES.md and docs/session-lifecycle-blockers.md record the blocked App identity.

Verification:

- `python3 scripts/consolidation-gates.py --write`
- `bash scripts/gh-app-token.sh --which`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`

## Source Next Action

Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
