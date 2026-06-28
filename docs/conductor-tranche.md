# Conductor Tranche

Generated: `2026-06-28T16:10:59+00:00`

Summary: `tranche-local-lifecycle-disk-pressure` -> `local-lifecycle-disk-pressure` (`drain`); stop before: Stop before local reclaim/deletion, broad generated build-out, GitHub merge/close, or any owner repo mutation not covered by a fresh owner receipt.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-local-lifecycle-disk-pressure` |
| Selected path | `local-lifecycle-disk-pressure` |
| Kind | `blocker` |
| Lane | `drain` |
| Score | `74` |
| Agent fit | `codex` |
| Attack index generated | `2026-06-28T16:10:52+00:00` |
| Ranked paths read | `33` |
| Skipped parked/observe/auth paths | `gen-organvm-session-meta-simplify-0628-e73d`, `cloud-credential-handles-unconfigured`, `credential-codex-auth-sessions`, `auth_credentials` |

## Work Packet

Purpose: Drive local lifecycle pressure down by converting the highest-risk roots into owner receipts, preservation proof, or explicit human-gated reclaim packets.

Repo/worktree: `organvm/limen` conductor checkout plus read-only inspection of `~/Workspace/.limen-worktrees`.

Allowed files:

- `scripts/*lifecycle*.py`
- `scripts/worktree-debt.py`
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

Stop condition: Stop before local reclaim/deletion, broad generated build-out, GitHub merge/close, or any owner repo mutation not covered by a fresh owner receipt.

Receipt: docs/worktree-lifecycle-ledger.md or docs/worktree-preservation-receipts.json for owner state; docs/conductor-tranche.md for the current packet.

Verification:

- `python3 scripts/worktree-debt.py --json`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`

## Source Next Action

Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
