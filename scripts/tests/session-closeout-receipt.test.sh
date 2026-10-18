#!/usr/bin/env bash
# session-closeout-receipt.test.sh — hermetic gate for scripts/session-closeout-receipt.py (the v2 receipt producer).
#
# Why it exists: the producer is only worth having if every receipt it emits is accepted by the REAL
# limen.session_closeout checker and every way that checker could be fooled (or crash) is refused first. The
# pytest module builds real git repositories with GitHub-style origins, fakes only `gh`, the conduct broker and
# the process census, and drives plan -> attest -> build -> commit -> push -> check. No network, no broker, no
# secrets. The producer validates portable custody bundles (pydantic) and reads the gate registry (PyYAML), so
# the pytest interpreter is resolved here exactly like sealed-custody.test.sh resolves its own, then handed to the
# hermetic runner as `python3`.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
cd "$ROOT"

PY=""
for candidate in "${LIMEN_SESSION_CLOSEOUT_RECEIPT_PYTHON:-}" "${LIMEN_GATE_PYTHON:-}" "$ROOT/cli/.venv/bin/python" \
  "${LIMEN_ROOT:-/nonexistent}/cli/.venv/bin/python" "$HOME/Workspace/limen/cli/.venv/bin/python" \
  python3.13 python3 python3.12 python3.11 python3.14; do
  [ -n "$candidate" ] || continue
  if "$candidate" -c "
import sys
sys.path.insert(0, '$ROOT/cli/src')
import limen.portable_custody, limen.process_ownership, limen.conduct.client, yaml, pytest
" >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done
[ -n "$PY" ] || { echo "FAIL: no python with limen + pydantic + PyYAML + pytest (set LIMEN_SESSION_CLOSEOUT_RECEIPT_PYTHON)" >&2; exit 1; }

# The hermetic runner scrubs every LIMEN_* variable and calls `python3 -m pytest`: put the chosen interpreter first.
PATH="$(dirname "$PY"):$PATH" exec bash "$ROOT/scripts/run-pytest-hermetic.sh" \
  scripts/tests/test_session_closeout_receipt.py -q
