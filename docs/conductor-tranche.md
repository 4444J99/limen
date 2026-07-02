# Conductor Tranche

Generated: `2026-07-02T16:11:53+00:00`

Summary: `tranche-github-consolidation-collisions` -> `github-consolidation-collisions` (`consolidation-gate`); stop before: Stop before `gh repo rename`, `consolidate-github.py --apply`, `rewrite-owners.py --apply`, GitHub App install, or credential writes unless a human explicitly opens that gate in-session.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Close incident classes with reusable receipts and gates, not one-lane symptom patches.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-github-consolidation-collisions` |
| Selected path | `github-consolidation-collisions` |
| Kind | `blocker` |
| Lane | `consolidation-gate` |
| Score | `78` |
| Agent fit | `codex/human-gate` |
| Attack index generated | `2026-07-02T16:11:35+00:00` |
| Ranked paths read | `49` |
| Skipped family/human-gate/parked/observe/auth paths | `worktree_lifecycle`, `session_lifecycle`, `github-app-limen-bot-not-wired`, `github_review`, `agent_coordination`, `local-lifecycle-disk-pressure`, `technical_debt_ci`, `convergence_corpus`, `gen-organvm-universal-mail--automation-test-coverage-0625-151e`, `cloud-runtime-endpoint-unconfigured`, `uncategorized`, `cloud-credential-handles-unconfigured`, `credential-codex-auth-sessions`, `resolve-organvm-i-theoria-.github-459-1ade`, `auth_credentials`, `cifix-organvm-i-theoria-conversation-corpus-engine-f02e`, `discover-organvm-kerygma-profiles-6c74`, `bld-my--father-mother-harden-44b2`, `bld-promptscope-next-rev-3fde` |

## Work Packet

Purpose: Advance the GitHub/org consolidation enforcement path by refreshing dry-run gates, surfacing collisions, and packetizing the exact human-gated rename/transfer/rewrite sequence.

Repo/worktree: `organvm/limen` conductor checkout only; GitHub/org state is read-only.

Allowed files:

- `scripts/consolidation-gates.py`
- `scripts/consolidate-github.py`
- `scripts/rewrite-owners.py`
- `scripts/session-blockers-ledger.py`
- `scripts/session-attack-paths.py`
- `scripts/conductor-tranche.py`
- `docs/consolidation/RUNBOOK.md`
- `docs/consolidation/COLLISION-RENAMES.md`
- `docs/consolidation/GATES.md`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `.limen-private/session-corpus/lifecycle/consolidation-gates.json`
- `.limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json`
- `.limen-private/session-corpus/lifecycle/session-attack-paths.json`
- `.limen-private/session-corpus/lifecycle/conductor-tranche.json`

Forbidden:

- `/Users/4jp/Workspace/4444J99/portvs`
- `creative placement work`
- `plaintext secrets or credential values`
- `irreversible GitHub transfer/rename/App install/credential actions`
- `task-board mutation unless the direct request explicitly requires it`

Stop condition: Stop before `gh repo rename`, `consolidate-github.py --apply`, `rewrite-owners.py --apply`, GitHub App install, or credential writes unless a human explicitly opens that gate in-session.

Receipt: docs/consolidation/GATES.md plus docs/conductor-tranche.md; private parsed gate receipt under .limen-private/session-corpus/lifecycle/.

Verification:

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
- `PYTHONPATH=cli/src python3 scripts/consolidate-github.py`
- `PYTHONPATH=cli/src python3 scripts/rewrite-owners.py`
- `bash scripts/gh-app-token.sh --which`

## Source Next Action

Resolve `docs/consolidation/COLLISION-RENAMES.md`, then require `PYTHONPATH=cli/src python3 scripts/consolidate-github.py` to report 0 collisions before any transfer.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/live-root-gate.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
