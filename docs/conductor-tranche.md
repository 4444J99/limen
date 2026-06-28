# Conductor Tranche

Generated: `2026-06-28T16:24:07+00:00`

Summary: `tranche-worktree-remote-branches-missing` -> `worktree-remote-branches-missing` (`blocker`); stop before: Stop before deletion, force-push, merge, or owner-repo source edits unless a narrower owner packet names the repo, branch, predicate, and receipt.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-worktree-remote-branches-missing` |
| Selected path | `worktree-remote-branches-missing` |
| Kind | `blocker` |
| Lane | `blocker` |
| Score | `70` |
| Agent fit | `codex` |
| Attack index generated | `2026-06-28T16:23:10+00:00` |
| Ranked paths read | `31` |
| Skipped family/parked/observe/auth paths | `worktree_lifecycle`, `session_lifecycle`, `github_review`, `agent_coordination`, `technical_debt_ci`, `local-lifecycle-disk-pressure`, `convergence_corpus`, `uncategorized`, `cloud-credential-handles-unconfigured`, `credential-codex-auth-sessions`, `auth_credentials` |

## Work Packet

Purpose: Resolve the remaining worktree lifecycle blocker by converting affected roots into preservation proof, owner blockers, remote/default proof, or documented non-source residue.

Repo/worktree: `organvm/limen` conductor checkout plus read-only inspection of `~/Workspace/.limen-worktrees`.

Allowed files:

- `cli/src/limen/worktree_debt.py`
- `cli/tests/test_worktree_debt.py`
- `scripts/worktree-debt.py`
- `scripts/*lifecycle*.py`
- `docs/worktree-lifecycle-ledger.md`
- `docs/worktree-preservation-receipts.json`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `.limen-private/session-corpus/lifecycle/**`

Forbidden:

- `/Users/4jp/Workspace/4444J99/portvs`
- `creative placement work`
- `plaintext secrets or credential values`
- `irreversible GitHub transfer/rename/App install/credential actions`
- `task-board mutation unless the direct request explicitly requires it`

Stop condition: Stop before deletion, force-push, merge, or owner-repo source edits unless a narrower owner packet names the repo, branch, predicate, and receipt.

Receipt: docs/worktree-lifecycle-ledger.md and docs/worktree-preservation-receipts.json.

Verification:

- `python3 scripts/worktree-debt.py --json`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`

## Source Next Action

Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
