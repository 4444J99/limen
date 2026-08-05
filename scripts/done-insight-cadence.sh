#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERIFY_ROOT="${LIMEN_INSIGHT_CADENCE_VERIFY_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/limen-insight-cadence.XXXXXX")}"
export LIMEN_ROOT="$VERIFY_ROOT"
export LIMEN_TASKS="$VERIFY_ROOT/tasks.yaml"
LOGS="$LIMEN_ROOT/logs"
STATE="$LOGS/insight-cadence-state.json"
OUT_DIR="$LOGS/insight-cadence"
TOOL="$SOURCE_ROOT/scripts/insight-cadence.py"
mkdir -p "$LOGS"
if [ -f "$SOURCE_ROOT/tasks.yaml" ]; then
    cp "$SOURCE_ROOT/tasks.yaml" "$LIMEN_TASKS" # task-writer-audit: allow-derived-sandbox
else
    printf 'version: "1.0"\ntasks: []\n' > "$LIMEN_TASKS" # task-writer-audit: allow-derived-sandbox
fi
echo "0. Verification sandbox retained at $VERIFY_ROOT"

echo "1. Run initially to ensure all tiers fire because they have never run"
python3 "$TOOL" --once

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
python3 "$TOOL" --once

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

echo "5. Lineage conduit (insights-drift --json -> logs/insights-drift.json -> gatherer)"
DRIFT_TOOL="$(command -v insights-drift 2>/dev/null || true)"
[ -z "$DRIFT_TOOL" ] && [ -x "$HOME/.local/bin/insights-drift" ] && DRIFT_TOOL="$HOME/.local/bin/insights-drift"
if [ -z "$DRIFT_TOOL" ]; then
    echo "   (insights-drift not deployed on this host — lineage checks skipped)"
else
    FIX="$(mktemp -d)"
    echo "   fixture sandbox retained at $FIX"
    python3 - "$FIX" <<'PY'
import json, pathlib, sys
fix = pathlib.Path(sys.argv[1])
def mani(stamp, frictions):
    d = fix / stamp
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({
        "snapshot_at": stamp, "stats": {"messages": 1}, "window": {},
        "areas": [{"name": "A"}], "key_pattern": "kp-" + stamp,
        "friction": frictions}))
# One friction re-worded across all three snapshots (must cluster + persist),
# one that appears once and vanishes (must resolve).
mani("2026-01-01T0000", [
    {"category": "Premature done claims", "description": "declares work done early with gaps"},
    {"category": "Auth interruptions", "description": "login errors break long runs"}])
mani("2026-02-01T0000", [
    {"category": "Premature or hollow completion claims", "description": "declares work done early with gaps"}])
mani("2026-03-01T0000", [
    {"category": "Hollow premature completion claims", "description": "declares work done early with gaps remaining"}])
PY
    OUT1="$FIX/drift1.json"; OUT2="$FIX/drift2.json"
    INSIGHTS_SNAPDIR="$FIX" "$DRIFT_TOOL" --json "$OUT1"
    INSIGHTS_SNAPDIR="$FIX" "$DRIFT_TOOL" --json "$OUT2"
    if ! cmp -s "$OUT1" "$OUT2"; then
        echo "ERROR: lineage output is not byte-idempotent"
        exit 1
    fi
    python3 - "$OUT1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["snapshot_count"] == 3, d["snapshot_count"]
rec, res = d["recurring"], d["resolved"]
assert any(f["reports"] == 3 and f["status"] == "persisting" for f in rec), \
    f"re-worded friction did not cluster across 3 snapshots: {rec}"
assert any("auth" in f["label"].lower() and f["status"] == "resolved" for f in res), \
    f"vanished friction not marked resolved: {res}"
print(f"   clustering ok: {len(rec)} recurring, {len(res)} resolved")
PY
    # End-to-end: the cadence organ refreshes the drift file and surfaces
    # recurring frictions in its reports.
    INSIGHTS_SNAPDIR="$FIX" python3 "$TOOL" --force hourly
    if [ ! -f "$LOGS/insights-drift.json" ]; then
        echo "ERROR: insight-cadence did not refresh logs/insights-drift.json"
        exit 1
    fi
    if ! grep -q "Recurring friction across 3 insights reports" "$OUT_DIR/hourly-latest.md"; then
        echo "ERROR: recurring friction missing from hourly report"
        exit 1
    fi
    if ! grep -q "Friction resolved since" "$OUT_DIR/hourly-latest.md"; then
        echo "ERROR: resolved friction missing from hourly report"
        exit 1
    fi
    echo "   conduit ok: lineage flows archive -> drift json -> cadence report"
fi

echo "insight-cadence verification passed"
exit 0
