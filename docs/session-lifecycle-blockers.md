# Session Lifecycle Blockers

Generated: `2026-06-28T15:50:46+00:00`

## Canonical Handling

- Auth, login, secret, key, token, password, deploy-account, and provider-access issues are parked here unless a task explicitly scopes that account action.
- This receipt records handles and counts only. It does not read, print, repair, rotate, or commit secret values.
- A parked blocker is not cancelled work. It is a named owner lane that must be resolved or superseded before the dependent lifecycle can close.

## Intake Inputs

- Prompt lifecycle index present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-lifecycle-index.json`.
- Codex lifecycle index present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/codex-session-lifecycle.json`.
- Session corpus inventory present: `True` at `~/Workspace/limen/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- GitHub consolidation gates present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/consolidation-gates.json`.
- Redacted local prompt coverage: `9489` files, `92795` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `6`.
- Remote receipts enabled: `True`; cloud receipts enabled: `True`.
- Session pressure hook wired: `True`; last pressure snapshot present: `True`.
- Local lifecycle footprint: `5.6 GiB`.
- Capability substrate detected: `11` roots, `1317` skill files, `45` plugin/MCP manifests.
- Capability resurfacing receipt present/current: `True`/`True`; activation candidates `30`.
- GitHub consolidation gate: `34` source repos, `13` collision groups, App token wired `False`.

## Parked / Hung Workstreams

- By category: `auth_credentials` 2, `cloud_runtime` 1, `github_app_identity` 1, `github_consolidation` 1, `local_lean` 1, `owner_state` 2, `worktree_lifecycle` 2.
- By status: `needs_human_gate` 2, `parked` 8.

| ID | Category | Status | Evidence | Owner | Route |
|---|---|---|---|---|---|
| `credential-codex-auth-sessions` | `auth_credentials` | `parked` | 405 Codex sessions classified as auth/credential work; states: ALIVE 1, CLOSED 364, PARKED 40 | credential workstream | Keep parked unless a future scoped task explicitly requires the account action. |
| `cloud-credential-handles-unconfigured` | `auth_credentials` | `parked` | 6 credential/deploy handles absent; 0 present. No values inspected. | credential workstream | Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it. |
| `cloud-runtime-endpoint-unconfigured` | `cloud_runtime` | `parked` | No runtime URL was configured for the last cloud receipt probe. | limen deployment workstream | Keep separate from session intake; configure/probe runtime only in a deploy/runtime task. |
| `worktree-remote-branches-missing` | `worktree_lifecycle` | `parked` | 4 git worktree roots did not have the same branch present on origin. | worktree lifecycle | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| `worktree-lifecycle-debt` | `worktree_lifecycle` | `parked` | 6 `.limen-worktrees` roots still carry lifecycle debt. | worktree lifecycle | Preserve or owner-record each root; no deletion of unique work. |
| `owner-state-dirty-session-meta` | `owner_state` | `parked` | session-meta has 1 dirty entries. | session-meta | Preserve in that owner repo before treating corpus substrate as clean. |
| `owner-state-dirty-knowledge-corpus` | `owner_state` | `parked` | knowledge-corpus has 3 dirty entries. | knowledge-corpus | Preserve in that owner repo before treating corpus substrate as clean. |
| `local-lifecycle-disk-pressure` | `local_lean` | `parked` | Local lifecycle stores use 5.6 GiB (2.4 GiB worktrees, 3.2 GiB private corpus). | local lifecycle | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| `github-consolidation-collisions` | `github_consolidation` | `needs_human_gate` | 34 source repos remain outside `organvm`; 13 name-collision groups block the transfer apply gate. | GitHub consolidation | Resolve `docs/consolidation/COLLISION-RENAMES.md`, then require `PYTHONPATH=cli/src python3 scripts/consolidate-github.py` to report 0 collisions before any transfer. |
| `github-app-limen-bot-not-wired` | `github_app_identity` | `needs_human_gate` | `gh-app-token --which` resolves to `pat (GITHUB_TOKEN fallback)`; 4 org Apps are installed, and `limen[bot]` is not wired. | limen[bot] App identity | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |

## Private Output

- Private blocker index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json`.
- The private index keeps structured evidence and source paths, still without secret values or raw prompt text.

## Commands

- Refresh source receipts first: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh private absorption receipt: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh GitHub consolidation gates: `python3 scripts/consolidation-gates.py --write`
- Refresh this blocker ledger: `python3 scripts/session-blockers-ledger.py --write`
