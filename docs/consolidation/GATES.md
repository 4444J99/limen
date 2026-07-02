# GitHub Consolidation Gates

Generated: `2026-07-02T18:44:31+00:00`

## Rule

- This is a read-only gate receipt for the conductor selector.
- Do not run repo rename, repo transfer, owner rewrite `--apply`, App install, or credential writes from this receipt alone.
- Human approval is still required for any irreversible GitHub/org/App/credential action.

## Current Gate State

| Gate | Value |
|---|---|
| Source repos outside `organvm` | `34` |
| Source owners scanned | `10` |
| Name collision groups | `13` |
| Collision packet complete | `True` |
| Collision packet keeper rows | `13` |
| Collision packet rename commands | `13` / required `13` |
| Rename target conflicts/unknown | `0` / `0` |
| Transfer apply gate open | `False` |
| `tasks.yaml` repo refs to rewrite post-transfer | `49` |
| Local remotes to rewrite post-transfer | `15` |
| Deploy literal to fix post-transfer | `False` |
| `gh-app-token --which` | `pat (GITHUB_TOKEN fallback)` |
| `limen[bot]` App installed | `False` |
| App token wired | `False` |
| Installed org Apps | `claude`, `google-labs-jules`, `oz-by-warp`, `chatgpt-codex-connector` |
| Blocking gates | `name-collisions`, `limen-bot-token-not-wired`, `limen-bot-app-not-installed`, `post-transfer-owner-rewrite-pending` |

## Collision Examples

- `content-engine--asset-amplifier`: `a-organvm/content-engine--asset-amplifier`, `organvm-iii-ergon/content-engine--asset-amplifier`
- `contrib--dapr-dapr`: `4444J99/contrib--dapr-dapr`, `a-organvm/contrib--dapr-dapr`
- `contrib--notion-mcp-server`: `4444J99/contrib--notion-mcp-server`, `a-organvm/contrib--notion-mcp-server`
- `hokage-chess`: `4444J99/hokage-chess`, `a-organvm/hokage-chess`
- `meta-organvm.github.io`: `meta-organvm/meta-organvm.github.io`, `organvm-i-theoria/meta-organvm.github.io`
- `organvm-ii-poiesis.github.io`: `organvm-i-theoria/organvm-ii-poiesis.github.io`, `organvm-ii-poiesis/organvm-ii-poiesis.github.io`
- `organvm-iii-ergon.github.io`: `organvm-i-theoria/organvm-iii-ergon.github.io`, `organvm-iii-ergon/organvm-iii-ergon.github.io`
- `organvm-iv-taxis.github.io`: `organvm-i-theoria/organvm-iv-taxis.github.io`, `organvm-iv-taxis/organvm-iv-taxis.github.io`
- `organvm-v-logos.github.io`: `organvm-i-theoria/organvm-v-logos.github.io`, `organvm-v-logos/organvm-v-logos.github.io`
- `organvm-vi-koinonia.github.io`: `organvm-i-theoria/organvm-vi-koinonia.github.io`, `organvm-vi-koinonia/organvm-vi-koinonia.github.io`
- `organvm-vii-kerygma.github.io`: `organvm-i-theoria/organvm-vii-kerygma.github.io`, `organvm-vii-kerygma/organvm-vii-kerygma.github.io`
- `sovereign--ground`: `4444J99/sovereign--ground`, `organvm-i-theoria/sovereign--ground`
- `studium-generale`: `4444J99/studium-generale`, `organvm-i-theoria/studium-generale`

## Collision Packet Check

- Packet path: `~/Workspace/limen/docs/consolidation/COLLISION-RENAMES.md`.
- Live collision groups parsed: `13` / `13`.
- Missing keeper rows: `0`.
- Invalid keeper rows: `0`.
- Missing rename commands: `0`.
- Extra rename commands: `0`.
- Rename target conflicts: `0`.
- Rename target probes unknown: `0`.

## Exact Gates

1. Resolve collision names from `docs/consolidation/COLLISION-RENAMES.md`.
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
