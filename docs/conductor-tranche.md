# Conductor Tranche

Generated: `2026-06-28T19:19:18+00:00`

Summary: `tranche-owner-state-dirty-session-meta` -> `owner-state-dirty-session-meta` (`blocker`); stop before: Stop before content rewriting, synthesis, deletion/revert of owner changes, broad corpus convergence, owner repo push/PR, or edits outside the listed dirty owner paths unless a new explicit owner packet opens that scope.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Close incident classes with reusable receipts and gates, not one-lane symptom patches.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-owner-state-dirty-session-meta` |
| Selected path | `owner-state-dirty-session-meta` |
| Kind | `blocker` |
| Lane | `blocker` |
| Score | `42` |
| Agent fit | `codex` |
| Attack index generated | `2026-06-28T19:19:18+00:00` |
| Ranked paths read | `30` |
| Skipped family/human-gate/parked/observe/auth paths | `session_lifecycle`, `worktree_lifecycle`, `github_review`, `github-app-limen-bot-not-wired`, `github-consolidation-collisions`, `agent_coordination`, `technical_debt_ci`, `local-lifecycle-disk-pressure`, `convergence_corpus`, `uncategorized`, `cloud-credential-handles-unconfigured`, `credential-codex-auth-sessions`, `auth_credentials` |

## Work Packet

Purpose: Preserve `owner-state-dirty-session-meta` as a scoped owner-state packet for `session-meta` without rewriting corpus content or broadening into creative placement work.

Repo/worktree: `session-meta` owner repo at `~/Workspace/session-meta` plus `organvm/limen` conductor receipts.

Allowed files:

- `~/Workspace/session-meta/ingest/manifest.jsonl`
- `~/Workspace/session-meta/scheduler/jules/harvest/3583067612331601751.diff`
- `~/Workspace/session-meta/scheduler/jules/harvest/GEN-organvm-session-meta-simplify-0627/`
- `docs/session-corpus-ledger.md`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `.limen-private/session-corpus/inventory/session-corpus-ledger.json`
- `.limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json`
- `.limen-private/session-corpus/lifecycle/session-attack-paths.json`
- `.limen-private/session-corpus/lifecycle/conductor-tranche.json`

Forbidden:

- `/Users/4jp/Workspace/4444J99/portvs`
- `creative placement work`
- `plaintext secrets or credential values`
- `irreversible GitHub transfer/rename/App install/credential actions`
- `task-board mutation unless the direct request explicitly requires it`

Stop condition: Stop before content rewriting, synthesis, deletion/revert of owner changes, broad corpus convergence, owner repo push/PR, or edits outside the listed dirty owner paths unless a new explicit owner packet opens that scope.

Receipt: `session-meta` owner branch/commit or patch receipt, plus refreshed docs/session-corpus-ledger.md, docs/session-lifecycle-blockers.md, and docs/conductor-tranche.md.

Verification:

- `git -C ~/Workspace/session-meta status --branch --short`
- `git -C ~/Workspace/session-meta diff --name-status`
- `git -C ~/Workspace/session-meta diff --check`
- `python3 scripts/session-corpus-ledger.py --write --all`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`

## Source Next Action

Preserve in that owner repo before treating corpus substrate as clean.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
