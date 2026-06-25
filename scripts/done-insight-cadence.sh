#!/usr/bin/env bash
# done-insight-cadence.sh — done-predicate for the insight-cadence organ.
#
# Forces each of the four tiers (hourly, daily, weekly, monthly) to fire once,
# asserts a report lands in logs/insight-cadence/ with >=1 insight carrying a
# valid owner, and is IDEMPOTENT (a 2nd run mutates nothing — already-due tiers
# fire again harmlessly because the window advances).
#
# Exit 0 IFF done. Prints "insight-cadence verification passed" on success.
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
cd "$LIMEN_ROOT" || exit 1

export PYTHONPATH="$LIMEN_ROOT/cli/src"
OUT_DIR="$LIMEN_ROOT/logs/insight-cadence"
mkdir -p "$OUT_DIR" 2>/dev/null || true

echo "═══ insight-cadence done-predicate $(date '+%F %T') ═══"

# Force each tier to fire
errors=0
for tier in hourly daily weekly monthly; do
  echo "── forcing tier: $tier ──"
  if ! python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --force-tier "$tier" 2>&1; then
    echo "ERROR: insight-cadence --force-tier $tier failed"
    errors=$(( errors + 1 ))
  fi
done

# Assert reports exist with >=1 insight and valid owner
echo ""
echo "── verifying reports ──"
reports_found=0
for tier in hourly daily weekly monthly; do
  latest=$(ls -t "$OUT_DIR/${tier}"-*.json 2>/dev/null | head -1)
  if [ -z "$latest" ]; then
    echo "ERROR: no report found for tier=$tier"
    errors=$(( errors + 1 ))
    continue
  fi
  count=$(python3 -c "
import json, sys
try:
    d = json.load(open('$latest'))
    ins = d.get('insights', [])
    print(len(ins))
    for i in ins:
        owner = i.get('owner', '')
        if not owner or not isinstance(owner, str) or len(owner.strip()) == 0:
            sys.stderr.write(f'invalid owner in insight: {i.get(\"id\", \"?\")}\n')
            sys.exit(1)
except Exception as e:
    sys.stderr.write(f'error reading $latest: {e}\n')
    sys.exit(1)
" 2>&1)
  rc=$?
  if [ "$rc" != 0 ]; then
    echo "ERROR: $latest validation failed"
    errors=$(( errors + 1 ))
  elif [ "$count" -ge 1 ]; then
    echo "  OK: $latest ($count insights, all owners valid)"
    reports_found=$(( reports_found + 1 ))
  else
    echo "ERROR: $latest has 0 insights"
    errors=$(( errors + 1 ))
  fi
done

if [ "$errors" -gt 0 ]; then
  echo ""
  echo "FAILED: $errors error(s) — insight-cadence NOT done"
  exit 1
fi

echo ""
echo "═══ insight-cadence verification passed ═══"
exit 0
