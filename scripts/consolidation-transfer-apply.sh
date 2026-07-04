#!/usr/bin/env bash
# Consolidation transfer — run ONLY after renames are complete and dry-run shows collisions = 0
# Generated from docs/consolidation/RUNBOOK.md gate 4 (verified 2026-07-02)
#
# This transfers all remaining source repos to organvm and applies source-owner topics.
# Prerequisite: consolidation-renames-apply.sh completed successfully + dry-run verified collisions = 0

set -euo pipefail

if [ "${LIMEN_CONSOLIDATION_GATE:-}" != "consolidation-gate-open" ]; then
  cat >&2 <<EOF
Refusing to run irreversible GitHub consolidation transfer.
Open the human consolidation gate first, then run:
  LIMEN_CONSOLIDATION_GATE=consolidation-gate-open bash $0
EOF
  exit 2
fi

echo "⚠ GitHub mutation gate: transfers are IRREVERSIBLE. Verify you have admin:org + workflow."
echo ""
echo "Running consolidation transfer (--apply)..."
cd /Users/4jp/Workspace/limen
PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply

echo ""
echo "✓ Transfer complete. 34 repos have been moved to organvm with source-owner topics."
echo "  Next: run consolidation-owner-rewrite-apply.sh to update local remotes + tasks.yaml refs."
