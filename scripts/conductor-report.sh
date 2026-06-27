#!/usr/bin/env bash
# Scheduled conductor report: validate the board vocabulary, verify dispatch state,
# and record harvest/heal readiness without silently recycling stale work.
set -uo pipefail

export LIMEN_ROOT="${LIMEN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
PY="$LIMEN_ROOT/cli/src"
REPORT_DIR="$LIMEN_ROOT/.limen-reports"
REPORT="$REPORT_DIR/conductor-report.txt"

mkdir -p "$REPORT_DIR" "$LIMEN_ROOT/logs"
: > "$REPORT"

run_step() {
  local label="$1"
  shift
  {
    echo
    echo "==> $label"
  } | tee -a "$REPORT"
  "$@" 2>&1 | tee -a "$REPORT"
  return "${PIPESTATUS[0]}"
}

fail=0

run_step "Validate task-board statuses" python3 "$LIMEN_ROOT/scripts/validate-task-board.py" || fail=1
run_step "Verify dispatch state" python3 "$LIMEN_ROOT/scripts/verify-dispatch.py" || fail=1

run_step "Pull completed Jules sessions" python3 "$LIMEN_ROOT/scripts/harvest-pull-completed.py" || {
  echo "harvest-pull-completed skipped or failed; see report above" | tee -a "$REPORT"
}
run_step "Harvest local Jules results" env PYTHONPATH="$PY" python3 -m limen.cli harvest --agent jules || {
  echo "limen harvest skipped or failed; see report above" | tee -a "$REPORT"
}
run_step "Preview dispatch heal" python3 "$LIMEN_ROOT/scripts/heal-dispatch.py" || {
  echo "heal-dispatch preview skipped or failed; see report above" | tee -a "$REPORT"
}

python3 - <<'PY' | tee -a "$REPORT"
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["LIMEN_ROOT"])
path = root / "logs" / "dispatch-verify.json"
data = json.loads(path.read_text())
counts = data.get("counts", {})
bad_keys = ("PR_MERGED", "PR_CLOSED", "PR_MISSING", "DISPATCHED_NO_PR", "CHRONIC")
bad = {key: int(counts.get(key, 0)) for key in bad_keys if int(counts.get(key, 0))}
print("\n==> Dispatch drift gate")
print(json.dumps(counts, sort_keys=True))
if bad:
    print(f"actionable dispatch drift detected: {bad}", file=sys.stderr)
    sys.exit(1)
print("no actionable dispatch drift")
PY
drift_status="${PIPESTATUS[0]}"
if [ "$drift_status" -ne 0 ]; then
  fail=1
fi

cp "$LIMEN_ROOT/logs/dispatch-verify.json" "$REPORT_DIR/dispatch-verify.json" 2>/dev/null || true

if [ "$fail" -ne 0 ]; then
  echo "conductor report failed" | tee -a "$REPORT"
  exit 1
fi

echo "conductor report passed" | tee -a "$REPORT"
