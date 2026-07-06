# Session Lifecycle Blockers

Generated: `2026-07-06T13:44:16+00:00`

## Canonical Handling

- Auth, login, secret, key, token, password, deploy-account, and provider-access issues are parked here unless a task explicitly scopes that account action.
- This receipt records handles and counts only. It does not read, print, repair, rotate, or commit secret values.
- A parked blocker is not cancelled work. It is a named owner lane that must be resolved or superseded before the dependent lifecycle can close.

## Intake Inputs

- Prompt lifecycle index present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-lifecycle-index.json`.
- Codex lifecycle index present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/codex-session-lifecycle.json`.
- Session corpus inventory present: `True` at `~/Workspace/limen/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- GitHub consolidation gates present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/consolidation-gates.json`.
- Network health receipt present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/network-health.json`.
- Dispatch health receipt present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/dispatch-health.json`.
- Live root gate receipt present: `True` at `~/Workspace/limen/.limen-private/session-corpus/lifecycle/live-root-gate.json`.
- Redacted local prompt coverage: `15223` files, `131021` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `1`.
- Remote receipts enabled: `True`; cloud receipts enabled: `True`.
- Session pressure hook wired: `True`; last pressure snapshot present: `True`.
- Local lifecycle footprint: `29.1 GiB`.
- Capability substrate detected: `11` roots, `1374` skill files, `47` plugin/MCP manifests.
- Capability resurfacing receipt present/current: `True`/`True`; activation candidates `30`.
- Local network substrate: status `healthy`, mode `observe`, route `en0` via `192.168.1.1`.
- Dispatch substrate: status `healthy`, launchd `running`, live root `main`, dirty entries `0`, async dry-run ok `True`.
- Live root gate: status `ready`, branch `main`, unique commits `0`, dirty entries `0`, launchd env drift `0`.
- GitHub consolidation gate: `0` source repos, `0` collision groups, collision packet complete `True`, App token wired `True`.

## Parked / Hung Workstreams

- By category: `auth_credentials` 2, `cloud_runtime` 1, `local_lean` 1, `worktree_lifecycle` 1.
- By status: `parked` 5.

| ID | Category | Status | Evidence | Owner | Route |
|---|---|---|---|---|---|
| `credential-codex-auth-sessions` | `auth_credentials` | `parked` | 405 Codex sessions classified as auth/credential work; states: ALIVE 1, CLOSED 364, PARKED 40 | credential workstream | Keep parked unless a future scoped task explicitly requires the account action. |
| `cloud-credential-handles-unconfigured` | `auth_credentials` | `parked` | 6 credential/deploy handles absent; 0 present. No values inspected. | credential workstream | Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it. |
| `cloud-runtime-endpoint-unconfigured` | `cloud_runtime` | `parked` | No runtime URL was configured for the last cloud receipt probe. | limen deployment workstream | Keep separate from session intake; configure/probe runtime only in a deploy/runtime task. |
| `worktree-lifecycle-debt` | `worktree_lifecycle` | `parked` | 1 `.limen-worktrees` roots still carry lifecycle debt. | worktree lifecycle | Preserve or owner-record each root; no deletion of unique work. |
| `local-lifecycle-disk-pressure` | `local_lean` | `parked` | Local lifecycle stores use 29.1 GiB (20.7 GiB worktrees, 8.4 GiB private corpus). | local lifecycle | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |

## Private Output

- Private blocker index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json`.
- The private index keeps structured evidence and source paths, still without secret values or raw prompt text.

## Commands

- Refresh source receipts first: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh private absorption receipt: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh local network health: `python3 scripts/network-health.py --write`
- Refresh dispatch health: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh live root gate: `python3 scripts/live-root-gate.py --write`
- Refresh GitHub consolidation gates: `python3 scripts/consolidation-gates.py --write`
- Refresh this blocker ledger: `python3 scripts/session-blockers-ledger.py --write`
