#!/usr/bin/env bash
set -euo pipefail

python3 scripts/check-runtime-lag.py
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
