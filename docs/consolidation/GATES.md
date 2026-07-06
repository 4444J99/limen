# GitHub Consolidation Gates

Generated: `2026-07-06T13:44:13+00:00`

## Rule

- This is a read-only gate receipt for the conductor selector.
- Do not run repo rename, repo transfer, owner rewrite `--apply`, App install, or credential writes from this receipt alone.
- Human approval is still required for any irreversible GitHub/org/App/credential action.

## Current Gate State

| Gate | Value |
|---|---|
| Source repos outside `organvm` | `0` |
| Source owners scanned | `10` |
| Name collision groups | `0` |
| Collision packet complete | `True` |
| Collision packet keeper rows | `13` |
| Collision packet rename commands | `13` / required `0` |
| Rename target conflicts/unknown | `0` / `0` |
| Transfer apply gate open | `True` |
| `tasks.yaml` repo refs to rewrite post-transfer | `0` |
| Local remotes to rewrite post-transfer | `0` |
| Deploy literal to fix post-transfer | `False` |
| `gh-app-token --which` | `app (limen[bot] installation token)` |
| `limen[bot]` App installed | `True` |
| App token wired | `True` |
| Installed org Apps | `claude`, `google-labs-jules`, `oz-by-warp`, `chatgpt-codex-connector`, `limen-conductor` |
| Blocking gates | none |

## Collision Examples

- none

## Collision Packet Check

- Packet path: `~/Workspace/limen/docs/consolidation/COLLISION-RENAMES.md`.
- Live collision groups parsed: `0` / `0`.
- Missing keeper rows: `0`.
- Invalid keeper rows: `0`.
- Missing rename commands: `0`.
- Extra rename commands: `0`.
- Rename target conflicts: `0`.
- Rename target probes unknown: `0`.

## Exact Gates

1. Collision names are resolved; keep `docs/consolidation/COLLISION-RENAMES.md` as the historical rename receipt.
2. Re-run `PYTHONPATH=cli/src python3 scripts/consolidate-github.py` and require `name collisions (must rename before transfer): 0`.
3. Only after the human transfer gate, run `PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply`.
4. Only after transfer, run `PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/limen-remotes.sh`.
5. Wire `limen[bot]` only after the GitHub App exists, is installed on `organvm`, and `GITHUB_APP_ID`/`GITHUB_APP_PRIVATE_KEY` are hydrated.
6. Require `bash scripts/gh-app-token.sh --which` to report `app (limen[bot] installation token)` before calling the App path wired.

## Probe Commands

- Consolidation dry-run: `/opt/homebrew/opt/python@3.14/bin/python3.14 scripts/consolidate-github.py`
- Owner rewrite dry-run: `/opt/homebrew/opt/python@3.14/bin/python3.14 scripts/rewrite-owners.py`
- App token path probe: `bash scripts/gh-app-token.sh --which`
- Org App installation probe: `gh api /orgs/organvm/installations --jq .installations[] | .app_slug`

## Private Output

- Private gate index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/consolidation-gates.json`.
- The private index keeps parsed counts and command metadata only; no secret values are read or stored.
