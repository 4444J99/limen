#!/usr/bin/env bash
# scripts/tests/check-heal-retirement.test.sh — test suite for check-heal-retirement.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LIMEN_ROOT="$ROOT"

echo "=== running check-heal-retirement.test.sh ==="
python3 "$ROOT/scripts/check-heal-retirement.py" --quiet
echo "PASS: check-heal-retirement.test.sh"
