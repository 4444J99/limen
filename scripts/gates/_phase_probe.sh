#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "FAIL: phase id is required (e.g., alpha)" >&2
  exit 2
fi

PHASE_ID="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLAN_PATH="$ROOT/docs/continuations/collaboration-operations-platform-alpha-omega-20260803/execution-dag.yaml"

python3 - "$PLAN_PATH" "$PHASE_ID" <<'PYCODE'
import json
import re
import sys
from pathlib import Path
import yaml

plan_path = Path(sys.argv[1])
phase_id = Path(sys.argv[2]).name.lower().replace('.sh','')
receipt_root = Path('receipts/packets')

plan = yaml.safe_load(plan_path.read_text(encoding='utf-8'))
phases = plan.get('phases') or []
selected = next((p for p in phases if (p.get('id') or '').lower() == phase_id), None)
if selected is None:
    print(f"FAIL: unknown phase {phase_id}", file=sys.stderr)
    raise SystemExit(1)

packets = selected.get('packets') or []
missing = []
non_done = []
for packet in packets:
    pid = str(packet.get('id') or '').lower()
    if not re.fullmatch(r"[a-z]+-[0-9]{2}", pid):
        print(f"FAIL: invalid packet id {packet.get('id')!r} in {phase_id}", file=sys.stderr)
        raise SystemExit(1)
    receipt_path = receipt_root / f"{pid}.json"
    if not receipt_path.exists():
        missing.append(packet.get('id'))
        continue
    try:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {packet.get('id')} receipt is invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    status = str(receipt.get('status') or '').strip().lower()
    if status != 'done':
        non_done.append((packet.get('id'), status or 'missing'))

if missing:
    print(f"FAIL: {phase_id} incomplete (missing receipts: {', '.join(missing)})", file=sys.stderr)
    raise SystemExit(1)
if non_done:
    details = ', '.join(f"{pid}={status}" for pid, status in non_done)
    print(f"FAIL: {phase_id} incomplete (non-done packets: {details})", file=sys.stderr)
    raise SystemExit(1)

print(f"PASS: {phase_id} phase predicate complete")
PYCODE
