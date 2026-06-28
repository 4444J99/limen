# Collision Rename Packet - remaining source repos

Live status verified 2026-06-28 with:

```bash
PYTHONPATH=cli/src python3 scripts/consolidate-github.py
```

Current result: 34 repos remain outside `organvm`, with 13 name-collision groups. All rename targets below were checked against the live source owners plus `organvm` and were free at verification time.

Mode: packet only. Do not run these commands without an explicit human GitHub mutation gate.

## Canonical Keepers

| Collision | Keeper |
|---|---|
| `meta-organvm.github.io` | `meta-organvm/meta-organvm.github.io` |
| `organvm-ii-poiesis.github.io` | `organvm-ii-poiesis/organvm-ii-poiesis.github.io` |
| `organvm-iii-ergon.github.io` | `organvm-iii-ergon/organvm-iii-ergon.github.io` |
| `organvm-iv-taxis.github.io` | `organvm-iv-taxis/organvm-iv-taxis.github.io` |
| `organvm-v-logos.github.io` | `organvm-v-logos/organvm-v-logos.github.io` |
| `organvm-vi-koinonia.github.io` | `organvm-vi-koinonia/organvm-vi-koinonia.github.io` |
| `organvm-vii-kerygma.github.io` | `organvm-vii-kerygma/organvm-vii-kerygma.github.io` |
| `content-engine--asset-amplifier` | `organvm-iii-ergon/content-engine--asset-amplifier` |
| `contrib--dapr-dapr` | `a-organvm/contrib--dapr-dapr` |
| `contrib--notion-mcp-server` | `a-organvm/contrib--notion-mcp-server` |
| `hokage-chess` | `a-organvm/hokage-chess` |
| `sovereign--ground` | `organvm-i-theoria/sovereign--ground` |
| `studium-generale` | `organvm-i-theoria/studium-generale` |

## Exact Rename Commands

Run only after confirming the GitHub mutation gate. These are renames only; they do not transfer repos.

```bash
# Pages shadow copies under organvm-i-theoria.
gh repo rename pages--theoria-copy--meta-organvm  --repo organvm-i-theoria/meta-organvm.github.io
gh repo rename pages--theoria-copy--poiesis       --repo organvm-i-theoria/organvm-ii-poiesis.github.io
gh repo rename pages--theoria-copy--ergon         --repo organvm-i-theoria/organvm-iii-ergon.github.io
gh repo rename pages--theoria-copy--taxis         --repo organvm-i-theoria/organvm-iv-taxis.github.io
gh repo rename pages--theoria-copy--logos         --repo organvm-i-theoria/organvm-v-logos.github.io
gh repo rename pages--theoria-copy--koinonia      --repo organvm-i-theoria/organvm-vi-koinonia.github.io
gh repo rename pages--theoria-copy--kerygma       --repo organvm-i-theoria/organvm-vii-kerygma.github.io

# Product/contrib duplicates.
gh repo rename content-engine--asset-amplifier--a-organvm-legacy --repo a-organvm/content-engine--asset-amplifier
gh repo rename contrib--dapr-dapr--4444j99-fork                  --repo 4444J99/contrib--dapr-dapr
gh repo rename contrib--notion-mcp-server--4444j99-fork          --repo 4444J99/contrib--notion-mcp-server
gh repo rename hokage-chess--4444j99                             --repo 4444J99/hokage-chess
gh repo rename sovereign--ground--4444j99                        --repo 4444J99/sovereign--ground
gh repo rename studium-generale--4444j99                         --repo 4444J99/studium-generale
```

## Required Recheck

Immediately after the renames:

```bash
cd ~/Workspace/limen
PYTHONPATH=cli/src python3 scripts/consolidate-github.py
```

Required output before transfer: `name collisions (must rename before transfer): 0`.

If any collision remains, do not transfer. Update this packet from the new dry-run output.
