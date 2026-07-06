#!/usr/bin/env bash
# workflow-runner.sh — Orchestrate health organ workflows.
#
# Runs the specified workflow and stamps the output through the safety sentinel.
#
# Usage:
#   ./organs/health/workflow-runner.sh [command]
#
# Commands:
#   all       — run all active workflows
#   posture   — run W1 (Intake → posture) — refresh the posture brief
#   state     — run W2 (State → record) — run the daily state beat
#   protocol  — run W3 (Protocol → adherence) — scan and update adherence log
#   calendar  — run W4 (Appointments → calendar) — rebuild appointment calendar
#   accommodation — run W5 (Accommodation → documentation)
#   status    — show current organ status and last-run times
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HEALTH="$ROOT/organs/health"
CASE="$HEALTH/cases/01-post-injury"
SENTINEL="$HEALTH/safety-sentinel.sh"
NOW="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

# Ensure the safety sentinel is executable
chmod +x "$SENTINEL"

# ── Exec the Executive Health Office engine for state/digest/reports ────────
# health-organ.py is the organ's primary execution engine — it reads the chart
# (off-repo, $LIMEN_HEALTH_DIR), derives state, and writes products (off-repo).
# It also stamps logs/health-organ-state.json and logs/.voice/health for
# proprioception (organ-health.py reads these).
run_health_office() {
  echo "  → Running health-organ.py (Executive Health Office)..."
  if python3 "$ROOT/scripts/health-organ.py" 2>&1; then
    echo "    ✓ Health office produced briefing, digest, and regimen"
  else
    echo "    ⚠ health-organ.py exited non-zero (fail-open — office may not be configured)"
  fi
}

# ── W1: Intake → posture ────────────────────────────────────────────────────
run_posture() {
  echo "  → W1: Intake → posture"
  if [ -f "$CASE/posture.md" ]; then
    echo "    ✓ posture.md exists — update on material health event"
    echo "    Last updated: $(stat -f "%Sm" "$CASE/posture.md" 2>/dev/null || echo "unknown")"
  else
    echo "    ✗ posture.md not found — create from template"
  fi
  # Safety sentinel
  if [ -f "$CASE/posture.md" ]; then
    "$SENTINEL" "$CASE/posture.md" 2>&1 | sed 's/^/    /'
  fi
}

# ── W2: State → record ──────────────────────────────────────────────────────
run_state() {
  echo "  → W2: State → record"
  LOG="$CASE/state-log.yaml"
  if [ -f "$LOG" ]; then
    ENTRIES=$(grep -c "^- .*timestamp:" "$LOG" 2>/dev/null || echo 0)
    echo "    ✓ $ENTRIES state entries recorded"
    "$SENTINEL" "$LOG" --check-only 2>&1 | sed 's/^/    /'
  else
    echo "    - No state log yet — first entry will be created on patient report"
  fi
}

# ── W3: Protocol → adherence ─────────────────────────────────────────────────
run_protocol() {
  echo "  → W3: Protocol → adherence"
  LOG="$CASE/protocol-log.md"
  if [ -f "$LOG" ]; then
    echo "    ✓ protocol-log.md exists"
    "$SENTINEL" "$LOG" --check-only 2>&1 | sed 's/^/    /'
  else
    echo "    - No protocol log yet — create when protocol is prescribed"
  fi
}

# ── W4: Appointments → calendar ──────────────────────────────────────────────
run_calendar() {
  echo "  → W4: Appointments → calendar"
  CAL="$CASE/calendar.md"
  if [ -f "$CAL" ]; then
    echo "    ✓ calendar.md exists"
  else
    echo "    - No appointment calendar yet"
    echo "    To create: list appointments and their providers"
  fi
}

# ── W5: Accommodation → documentation ────────────────────────────────────────
run_accommodation() {
  echo "  → W5: Accommodation → documentation"
  LOG="$CASE/accommodation-log.md"
  if [ -f "$LOG" ]; then
    REQUESTS=$(grep -c "^| A[0-9]" "$LOG" 2>/dev/null || echo 0)
    echo "    ✓ $REQUESTS accommodation requests tracked"
    echo "    → Linked to legal organ: organs/legal/ consumes this record for ADA matter"
    "$SENTINEL" "$LOG" --check-only 2>&1 | sed 's/^/    /'
  else
    echo "    - No accommodation record yet"
  fi
}

# ── Status ───────────────────────────────────────────────────────────────────
run_status() {
  echo "=== Health Organ Status ==="
  echo "Timestamp: $NOW"
  echo ""
  echo "Posture:"
  if [ -f "$CASE/posture.md" ]; then
    grep "^\\*\\*" "$CASE/posture.md" 2>/dev/null | head -5 | sed 's/^/  /'
  fi
  echo ""
  echo "Artifacts:"
  for f in posture.md state-log.yaml protocol-log.md calendar.md accommodation-log.md beat-log.yaml; do
    if [ -f "$CASE/$f" ]; then
      echo "  ✓ $f"
    else
      echo "  ○ $f (not yet created)"
    fi
  done
  echo ""
  echo "Safety sentinel:"
  if [ -x "$SENTINEL" ]; then
    echo "  ✓ safety-sentinel.sh (executable)"
  fi
  echo ""
  echo "Executive Health Office:"
  if [ -f "$ROOT/logs/health-organ-state.json" ]; then
    LAST=$(stat -f "%Sm" "$ROOT/logs/health-organ-state.json" 2>/dev/null || echo "unknown")
    echo "  ✓ health-organ.py last ran: $LAST"
  else
    echo "  ○ health-organ.py has not run yet (no chart configured?)"
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-status}" in
  all)
    echo "=== Running all health organ workflows ==="
    echo ""
    run_health_office
    echo ""
    run_posture
    echo ""
    run_state
    echo ""
    run_protocol
    echo ""
    run_calendar
    echo ""
    run_accommodation
    echo ""
    echo "=== All workflows complete ==="
    ;;
  posture) run_posture ;;
  state) run_health_office; run_state ;;
  protocol) run_protocol ;;
  calendar) run_calendar ;;
  accommodation) run_accommodation ;;
  status|--status|-s) run_status ;;
  *)
    echo "Unknown command: $1"
    echo "Usage: $0 {all|posture|state|protocol|calendar|accommodation|status}"
    exit 1
    ;;
esac
