#!/usr/bin/env bash
# scripts/tests/check-heal-retirement.test.sh — gate entrypoint for the retirement predicate.
#
# This used to BE the predicate: it ran check-heal-retirement.py --quiet against the LIVE board and
# asserted exit 0. That is not a test — it cannot fail for a code reason, it cannot pass until the
# entire backlog is drained, and --quiet suppressed the reason, so CI showed a bare FAIL with no
# diagnostic (PR #2144, pr-gate run 31310529140). The real fixtures live in the .test.py beside it,
# which is hermetic: no network, no live board, and every case attacks the predicate's core
# inference ("absent from the open set ⟹ closed ⟹ retire").
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LIMEN_ROOT="$ROOT"

echo "=== running check-heal-retirement.test.sh ==="
python3 "$ROOT/scripts/tests/check-heal-retirement.test.py"
echo "PASS: check-heal-retirement.test.sh"
