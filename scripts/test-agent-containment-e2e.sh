#!/usr/bin/env bash
# ==============================================================================
# test-agent-containment-e2e.sh
# E2E Test Harness for Provider-Agnostic Agent Containment & Surface Unification
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIMEN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_FILE="${LIMEN_ROOT}/tests/test_agent_containment_e2e.py"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  -t, --tier <1|2|3|4>    Run only tests for a specific tier
                          1: Feature coverage (R1-R5)
                          2: Boundary and corner cases
                          3: Cross-feature combinations
                          4: Real-world 8-consumer scenarios
  -k <pattern>            Run pytest matching the given keyword expression
  -v, --verbose           Verbose pytest output
  -q, --quiet             Quiet pytest output
  -h, --help              Display this help message

Examples:
  $(basename "$0")              # Run full 4-tier E2E test suite
  $(basename "$0") --tier 1     # Run only Tier 1 feature tests
  $(basename "$0") -k "codex"   # Run only tests matching 'codex'
EOF
  exit 0
}

TIER=""
KEYWORD=""
VERBOSITY="-v"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--tier)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 1
      fi
      TIER="$2"
      shift 2
      ;;
    -k)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 1
      fi
      KEYWORD="$2"
      shift 2
      ;;
    -v|--verbose)
      VERBOSITY="-vv"
      shift
      ;;
    -q|--quiet)
      VERBOSITY="-q"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

TARGET_EXPR=""
if [[ -n "${TIER}" ]]; then
  case "${TIER}" in
    1) TARGET_EXPR="TestTier1FeatureCoverage" ;;
    2) TARGET_EXPR="TestTier2BoundaryAndCornerCases" ;;
    3) TARGET_EXPR="TestTier3CrossFeatureCombinations" ;;
    4) TARGET_EXPR="TestTier4RealWorldConsumerScenarios" ;;
    *)
      echo "Error: Invalid tier '${TIER}'. Must be 1, 2, 3, or 4." >&2
      exit 1
      ;;
  esac
fi

if [[ -n "${KEYWORD}" ]]; then
  if [[ -n "${TARGET_EXPR}" ]]; then
    TARGET_EXPR="${TARGET_EXPR} and ${KEYWORD}"
  else
    TARGET_EXPR="${KEYWORD}"
  fi
fi

echo "========================================================================"
echo " Running Agent Containment E2E Test Suite"
echo " Test File: ${TEST_FILE}"
if [[ -n "${TARGET_EXPR}" ]]; then
  echo " Filter:    -k \"${TARGET_EXPR}\""
fi
echo "========================================================================"

PYTEST_ARGS=(
  "${TEST_FILE}"
  "${VERBOSITY}"
  "--tb=short"
)

if [[ -n "${TARGET_EXPR}" ]]; then
  PYTEST_ARGS+=("-k" "${TARGET_EXPR}")
fi

cd "${LIMEN_ROOT}"
EXIT_CODE=0
pytest "${PYTEST_ARGS[@]}" || EXIT_CODE=$?

echo "========================================================================"
if [[ ${EXIT_CODE} -eq 0 ]]; then
  echo " [PASS] All agent containment E2E tests succeeded."
else
  echo " [FAIL] E2E test failures detected (exit code: ${EXIT_CODE})."
fi
echo "========================================================================"

exit ${EXIT_CODE}

