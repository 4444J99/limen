#!/usr/bin/env bash
set -euo pipefail

python3 scripts/check-runtime-lag.py
python3 - <<'PY'
import json
from pathlib import Path

expected = "bc19871ac688f6a0892d61bffdd699070b6df620"
receipt = Path.home() / ".local/share/limen/current/receipt.json"
if not receipt.is_file():
    raise SystemExit("runtime receipt missing")
actual = json.loads(receipt.read_text()).get("sha")
if actual != expected:
    raise SystemExit(f"runtime SHA mismatch: expected {expected}, got {actual}")
print(f"runtime SHA: {actual}")
PY
python3 scripts/handoff-relay.py --check
python3 -m pytest \
  cli/tests/test_mcp_estate_contract.py \
  cli/tests/test_mcp_server.py \
  cli/tests/test_mcp_server_boot.py \
  cli/tests/test_mcp_native_observer.py \
  cli/tests/test_mcp_opencode_observer.py \
  cli/tests/test_mcp_gateway_evidence.py \
  cli/tests/test_mcp_effective_configuration.py \
  cli/tests/test_mcp_process_custody.py \
  -q
