#!/usr/bin/env bash
# UMA_MAIL_TRIAGE_WRAPPER
# Limen compatibility wrapper for UMA mail proof receipts.
set -uo pipefail

export HOME="${HOME:-/Users/4jp}"
LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
UMA_ROOT="${UMA_ROOT:-$HOME/Workspace/universal-mail--automation}"
PY="${LIMEN_PY:-python3}"
STATUS_OUT="${LIMEN_MAIL_STATUS_OUT:-$LIMEN_ROOT/logs/uma-mail-status.json}"
OPS_REPORT="${UMA_OPS_REPORT_PATH:-$HOME/System/Reports/mail-triage/latest.json}"
HISTORY_REPORT="${UMA_HISTORICAL_MAIL_PATH:-$HOME/System/Reports/mail-history/latest.json}"
MAX_AGE_HOURS="${LIMEN_MAIL_STATUS_MAX_AGE_HOURS:-24}"

uma_cmd_json() {
  if [ -n "${UMA_BIN:-}" ]; then
    printf '%s\n' "[\"$UMA_BIN\"]"
  elif [ -f "$UMA_ROOT/cli.py" ]; then
    "$PY" - "$PY" "$UMA_ROOT/cli.py" <<'PY'
import json
import sys

print(json.dumps([sys.argv[1], sys.argv[2]]))
PY
  else
    printf '%s\n' '["umail"]'
  fi
}

run_status() {
  "$PY" - "$STATUS_OUT" "$OPS_REPORT" "$HISTORY_REPORT" "$MAX_AGE_HOURS" "$(uma_cmd_json)" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

out = Path(sys.argv[1])
ops = sys.argv[2]
history = sys.argv[3]
max_age = sys.argv[4]
cmd = json.loads(sys.argv[5])
command = [
    *cmd,
    "mail-status",
    "--ops-report",
    ops,
    "--history",
    history,
    "--max-age-hours",
    max_age,
    "--output",
    str(out),
]
proc = subprocess.run(command, text=True, capture_output=True, check=False)
if proc.returncode not in (0, 2):
    out.parent.mkdir(parents=True, exist_ok=True)
    detail = (proc.stderr.strip() or proc.stdout.strip() or "unknown failure")[:500]
    fallback = {
        "schema": "uma.mail.status.v1",
        "status": "blocked",
        "mode": {"read_only": True, "mailbox_mutations": False, "sends": False},
        "privacy": {"redacted": True, "public_safe": True},
        "blockers": [
            {
                "surface": "uma_mail_status",
                "status": "blocked",
                "detail": detail,
            }
        ],
        "current_ops": {"available": False, "kpis": {}},
        "historical_crosswalk": {"available": False, "kpis": {}},
        "answers": {},
        "next_queue": [],
    }
    out.write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "blocked", "output": str(out), "returncode": proc.returncode}, sort_keys=True))
    raise SystemExit(0)

print(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else json.dumps({"status": "ok", "output": str(out)}))
PY
}

if [ "${1:-}" = "--census" ]; then
  "$PY" - "$LIMEN_ROOT" "$UMA_ROOT" "$STATUS_OUT" "$OPS_REPORT" "$HISTORY_REPORT" "$(uma_cmd_json)" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
uma = Path(sys.argv[2])
status_path = Path(sys.argv[3])
ops = Path(sys.argv[4])
history = Path(sys.argv[5])
cmd = json.loads(sys.argv[6])


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


status = load_json(status_path)
mode = status.get("mode") if isinstance(status.get("mode"), dict) else {}
current = status.get("current_ops") if isinstance(status.get("current_ops"), dict) else {}
historical = status.get("historical_crosswalk") if isinstance(status.get("historical_crosswalk"), dict) else {}
historical_kpis = historical.get("kpis") if isinstance(historical.get("kpis"), dict) else {}

print(json.dumps({
    "limen_root_present": root.exists(),
    "uma_root_present": uma.exists(),
    "uma_cli_present": (uma / "cli.py").exists() or bool(cmd),
    "uma_command": cmd[0] if cmd else None,
    "status_receipt_present": status_path.exists(),
    "status_schema": status.get("schema"),
    "status_value": status.get("status"),
    "current_ops_available": bool(current.get("available")),
    "historical_crosswalk_available": bool(historical.get("available")),
    "historical_reconciled": historical_kpis.get("reconciled"),
    "historical_source_messages": historical_kpis.get("source_messages"),
    "next_queue_count": len(status.get("next_queue") or []),
    "blocker_count": len(status.get("blockers") or []),
    "mailbox_mutations_allowed": bool(mode.get("mailbox_mutations")),
    "sends_allowed": bool(mode.get("sends")),
    "ops_report_present": ops.exists(),
    "history_report_present": history.exists(),
    "wrapper": True,
}, indent=2, sort_keys=True))
PY
  exit 0
fi

run_status || true
if [ -f "$LIMEN_ROOT/scripts/obligations-view.py" ]; then
  "$PY" "$LIMEN_ROOT/scripts/obligations-view.py" 2>&1 | tail -1 || true
fi
