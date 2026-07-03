#!/usr/bin/env bash
# Consolidation collision renames — run ONLY after consolidation-gate opens
# Generated from docs/consolidation/COLLISION-RENAMES.md (verified 2026-07-02)
#
# These 13 renames resolve the colliding repos so consolidate-github.py --apply can proceed.
# Order: Pages shadows first (organvm-i-theoria), then product/contrib duplicates.
# After renames complete, re-run: PYTHONPATH=cli/src python3 scripts/consolidate-github.py
# Required output: `name collisions (must rename before transfer): 0`

set -euo pipefail

echo "⚠ GitHub mutation gate: renames are IRREVERSIBLE. Verify you have admin:org + workflow before proceeding."
echo ""
echo "Pages shadow copies under organvm-i-theoria:"
gh repo rename pages--theoria-copy--meta-organvm  --repo organvm-i-theoria/meta-organvm.github.io
gh repo rename pages--theoria-copy--poiesis       --repo organvm-i-theoria/organvm-ii-poiesis.github.io
gh repo rename pages--theoria-copy--ergon         --repo organvm-i-theoria/organvm-iii-ergon.github.io
gh repo rename pages--theoria-copy--taxis         --repo organvm-i-theoria/organvm-iv-taxis.github.io
gh repo rename pages--theoria-copy--logos         --repo organvm-i-theoria/organvm-v-logos.github.io
gh repo rename pages--theoria-copy--koinonia      --repo organvm-i-theoria/organvm-vi-koinonia.github.io
gh repo rename pages--theoria-copy--kerygma       --repo organvm-i-theoria/organvm-vii-kerygma.github.io

echo ""
echo "Product/contrib duplicates:"
gh repo rename content-engine--asset-amplifier--a-organvm-legacy --repo a-organvm/content-engine--asset-amplifier
gh repo rename contrib--dapr-dapr--4444j99-fork                  --repo 4444J99/contrib--dapr-dapr
gh repo rename contrib--notion-mcp-server--4444j99-fork          --repo 4444J99/contrib--notion-mcp-server
gh repo rename hokage-chess--4444j99                             --repo 4444J99/hokage-chess
gh repo rename sovereign--ground--4444j99                        --repo 4444J99/sovereign--ground
gh repo rename studium-generale--4444j99                         --repo 4444J99/studium-generale

echo ""
echo "✓ Renames complete. Now re-run the dry-run to verify collisions = 0:"
echo "  PYTHONPATH=cli/src python3 scripts/consolidate-github.py"
