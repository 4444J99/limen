#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
python3 - <<'PY'
import json
from pathlib import Path

path = Path("docs/continuations/mcp-estate-closeout-20260910/workstream.json")
contract = json.loads(path.read_text())["contract"]
seconds = contract["runway"]["duration_seconds"]
if not isinstance(seconds, int) or seconds <= 0:
    raise SystemExit("invalid finite runway")
print(f"validated finite runway: {seconds}s")
PY
python3 scripts/live-root-gate.py --write --fetch
