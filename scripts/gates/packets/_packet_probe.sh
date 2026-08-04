#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "FAIL: packet id is required (e.g., alpha-01)" >&2
  exit 2
fi

PACKET_ID="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
PACKET_UPPER="$(printf '%s' "$PACKET_ID" | tr '[:lower:]' '[:upper:]')"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PLAN_PATH="$ROOT/docs/continuations/collaboration-operations-platform-alpha-omega-20260803/execution-dag.yaml"
RECEIPT_PATH="receipts/packets/${PACKET_ID}.json"

if [[ ! -f "$PLAN_PATH" ]]; then
  echo "FAIL: execution DAG missing: $PLAN_PATH" >&2
  exit 2
fi

# Shared deterministic sanity check for every packet.
if ! python3 "$ROOT/scripts/check-collaboration-operations-plan.py" --dag "$PLAN_PATH" >/tmp/collab-plan-check.log; then
  cat /tmp/collab-plan-check.log >&2
  exit 1
fi

python3 - "$PLAN_PATH" "$PACKET_UPPER" "$RECEIPT_PATH" <<'PY'
import json
import sys
from pathlib import Path
import yaml

doc_path = Path(sys.argv[1])
packet_id = sys.argv[2]
receipt_path = Path(sys.argv[3])

doc = yaml.safe_load(doc_path.read_text(encoding="utf-8")) or {}
packet_map = {}
phase_by_packet = {}
for phase in doc.get("phases", []):
    phase_id = phase.get("id")
    for packet in phase.get("packets", []):
        pid = packet.get("id")
        if isinstance(pid, str):
            packet_map[pid.upper()] = packet
            phase_by_packet[pid.upper()] = phase_id

packet = packet_map.get(packet_id)
if packet is None:
    print(f"FAIL: packet {packet_id} is not declared in execution DAG")
    raise SystemExit(1)

phase_id = phase_by_packet[packet_id]
packet_slug = packet_id.lower()
expected_receipt = f"receipts/packets/{packet_slug}.json"
expected_predicate = f"./scripts/gates/packets/{packet_slug}.sh"

if packet.get("receipt_target") != expected_receipt:
    print(f"FAIL: {packet_id} has non-canonical receipt_target {packet.get('receipt_target')!r}")
    raise SystemExit(1)
if packet.get("predicate") != expected_predicate:
    print(f"FAIL: {packet_id} has non-canonical predicate {packet.get('predicate')!r}")
    raise SystemExit(1)

if not receipt_path.is_file():
    print(f"SKIP: {packet_id} proof not yet recorded (expected {expected_receipt})")
    raise SystemExit(77)

try:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"FAIL: {packet_id} receipt is not valid JSON: {exc}")
    raise SystemExit(1)

status = str(receipt.get("status") or "").strip().lower()
if status != "done":
    print(f"FAIL: {packet_id} receipt status is {receipt.get('status')!r} (expected 'done')")
    raise SystemExit(1)

print(
    f"PASS: {packet_id} ({phase_id} / {packet.get('effect')}) completed; "
    f"receipt={receipt_path.as_posix()}"
)
PY
