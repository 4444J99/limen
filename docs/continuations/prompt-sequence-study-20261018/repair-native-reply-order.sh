#!/usr/bin/env bash
# Prepared owner handoff. Not executed by the study while admission is denied.
set -euo pipefail
mode="${1:---dry-run}"
case "$mode" in --dry-run|--apply) ;; *) echo "Use --dry-run or --apply" >&2; exit 64 ;; esac
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
root="$(git -C "$here" rev-parse --show-toplevel)"
patch="$here/native-reply-order.proposed.patch"
testfile="$here/test_native_projection.py"
git -C "$root" apply --check "$patch"
if [[ "$mode" == --dry-run ]]; then
  echo "Patch context is applicable. No source changed and no test executed."
  echo "Apply mode requires the owning worktree's admitted execution context."
  exit 0
fi
branch="$(git -C "$root" symbolic-ref --short HEAD)"
if [[ "$branch" == main || "$branch" == master ]]; then
  echo "Use the study's isolated topic worktree." >&2
  exit 77
fi
source "$root/scripts/lib/gate-python.sh"
gate_python="$(limen_gate_python)"
"$gate_python" -c 'import pytest'
export PATH="$(dirname -- "$gate_python"):$PATH"
python3 -c 'import os, sys; assert os.path.samefile(sys.executable, sys.argv[1])' "$gate_python"
mkdir -p -m 700 "$root/.limen-private/prompt-sequence-study"
receipts="$(mktemp -d "$root/.limen-private/prompt-sequence-study/reply-order-tests.XXXXXX")"
run_tests() {
  "$gate_python" - "$root" "$testfile" "$@" <<'PY'
import subprocess
import sys
from pathlib import Path

root, testfile, *args = sys.argv[1:]
try:
    result = subprocess.run(
        ["bash", str(Path(root) / "scripts/run-pytest-hermetic.sh"), testfile, "-q", *args],
        cwd=root,
        timeout=120,
        check=False,
    )
except subprocess.TimeoutExpired:
    raise SystemExit(124)
raise SystemExit(result.returncode)
PY
}
if run_tests -k 'later_prompt or later_commentary' --junitxml "$receipts/red.xml"; then
  echo "Baseline unexpectedly passed; do not apply the proposed repair." >&2
  exit 1
else
  red_status=$?
fi
if [[ "$red_status" != 1 ]]; then
  echo "Baseline did not fail by assertion; preserve diagnostics and stop." >&2
  exit "$red_status"
fi
"$gate_python" - "$receipts/red.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET

cases = list(ET.parse(sys.argv[1]).getroot().iter("testcase"))
expected = {
    "test_later_prompt_does_not_receive_an_earlier_native_turn_reply",
    "test_later_prompt_without_later_reply_keeps_its_outcome_missing",
    "test_rollout_later_commentary_does_not_inherit_an_earlier_final",
}
assert {case.attrib["name"] for case in cases} == expected
assert all(case.find("failure") is not None and case.find("error") is None for case in cases)
assert all(case.find("failure").attrib.get("message", "").startswith(("assert ", "AssertionError")) for case in cases)
PY
git -C "$root" apply "$patch"
run_tests --junitxml "$receipts/green.xml"
git -C "$root" diff --check
echo "Fixture file passed. Preserve red/green receipts at: $receipts"
echo "Affected native columns and the catalog still require regeneration and reconciliation."
