#!/usr/bin/env bash
# Consolidation owner-rewrite — run ONLY after transfer (--apply) completes
# Generated from docs/consolidation/RUNBOOK.md gate 5 (verified 2026-07-02)
#
# This rewrites tasks.yaml refs + local remotes, then generates a script to repoint checkouts.
# Prerequisite: consolidation-transfer-apply.sh completed successfully

set -euo pipefail

if [ "${LIMEN_CONSOLIDATION_GATE:-}" != "consolidation-gate-open" ]; then
  cat >&2 <<EOF
Refusing to run irreversible consolidation owner rewrite.
Open the human consolidation gate first, then run:
  LIMEN_CONSOLIDATION_GATE=consolidation-gate-open bash $0
EOF
  exit 2
fi

echo "⚠ GitHub mutation gate: rewrite is IRREVERSIBLE. Verify transfer completed before proceeding."
echo ""
echo "Running owner-rewrite (tasks.yaml refs + local remotes)..."
cd /Users/4jp/Workspace/limen
PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/limen-remotes.sh

echo ""
echo "Generated local-checkout repointing commands at /tmp/limen-remotes.sh"
echo "Review, then run: bash /tmp/limen-remotes.sh"
echo ""
echo "After remotes are repointed:"
echo "  1. Verify with: git remote -v (should show organvm/* instead of old owners)"
echo "  2. Run: PYTHONPATH=cli/src python3 scripts/rewrite-owners.py (dry-run to verify)"
echo "  3. Next: consolidation-app-wire.sh to install limen[bot] (gated on app existence + secrets)"
