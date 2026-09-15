#!/usr/bin/env bash
# lane-liveness.test.sh — hermetic distinction between idle, active, stalled, and unmeasured.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
bash "$root/scripts/run-pytest-hermetic.sh" "$root/cli/tests/test_lane_liveness.py" -q
echo "lane-liveness regression test PASSED"
