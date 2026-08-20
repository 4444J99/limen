#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CONTRACT="$ROOT/.limen-workstream/workstream.json"

python3 - "$CONTRACT" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

path = Path(sys.argv[1])
try:
    contract = json.loads(path.read_text(encoding="utf-8"))
    runway = contract["runway"]
except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"switch: invalid private runway contract: {exc}")

deadline = runway.get("deadline_epoch")
if deadline is None:
    print("switch: capsule is valid and not yet admitted")
    raise SystemExit(0)
if not isinstance(deadline, int):
    raise SystemExit("switch: deadline_epoch must be an integer or null")

remaining = deadline - int(time.time())
if remaining < 1800:
    print(f"switch: successor required; remaining_seconds={remaining}")
    raise SystemExit(75)
print(f"switch: runway healthy; remaining_seconds={remaining}")
PY
