#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

path = Path("docs/continuations/mcp-estate-closeout-20260910/workstream.json")
workstream = json.loads(path.read_text())
contract = workstream["contract"]
seconds = contract["runway"]["duration_seconds"]
if not isinstance(seconds, int) or seconds <= 0:
    raise SystemExit("invalid finite runway")
expected_branch = workstream["branch"]
actual_branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
if actual_branch != expected_branch:
    raise SystemExit(f"not in isolated capsule branch: expected {expected_branch}, got {actual_branch}")
print(f"validated finite runway: {seconds}s")
PY
python3 scripts/live-root-gate.py --write --fetch
