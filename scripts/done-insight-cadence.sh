#!/usr/bin/env bash
set -euo pipefail

export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
LOGS="$LIMEN_ROOT/logs"
STATE="$LOGS/insight-cadence-state.json"
OUT_DIR="$LOGS/insight-cadence"

# clean up
rm -rf "$OUT_DIR"
rm -f "$STATE"

echo "1. Run initially to ensure all tiers fire because they have never run"
python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once

echo "2. Assert files land in logs/insight-cadence/"
if [ ! -d "$OUT_DIR" ]; then
    echo "ERROR: Directory $OUT_DIR not created"
    exit 1
fi

for tier in hourly daily weekly monthly; do
    if ! ls "$OUT_DIR/${tier}-"*.json >/dev/null 2>&1; then
        echo "ERROR: Missing json report for tier $tier"
        exit 1
    fi
    if [ ! -f "$OUT_DIR/${tier}-latest.md" ]; then
        echo "ERROR: Missing markdown report for tier $tier"
        exit 1
    fi
done

echo "3. Assert at least one insight with a non-empty owner exists"
for json_file in "$OUT_DIR/"*.json; do
    owner=$(python3 -c "
import json
try:
    d = json.load(open('$json_file'))
    insights = d.get('insights', [])
    valid_owners = [i.get('owner') for i in insights if i.get('owner')]
    if valid_owners:
        print('found')
    else:
        print('none')
except Exception as e:
    print('error')
")
    if [ "$owner" != "found" ]; then
        echo "ERROR: File $json_file does not have an insight with a non-empty owner"
        exit 1
    fi
done

echo "4. Assert idempotency"
state_before=$(md5sum "$STATE" | awk '{print $1}')
files_before=$(find "$OUT_DIR" -type f | wc -l)

# Run again, shouldn't do anything because window hasn't elapsed
python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once

state_after=$(md5sum "$STATE" | awk '{print $1}')
files_after=$(find "$OUT_DIR" -type f | wc -l)

if [ "$state_before" != "$state_after" ]; then
    echo "ERROR: Idempotency failed: state changed"
    exit 1
fi

if [ "$files_before" != "$files_after" ]; then
    echo "ERROR: Idempotency failed: new files created"
    exit 1
fi

echo "insight-cadence verification passed"
exit 0
