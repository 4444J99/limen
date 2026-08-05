#!/usr/bin/env bash
# sync-hishand-dedup.test.sh — a stamped lever pointer must be RECOGNISED, never re-minted.
#
# Guards the #892/#827 duplicate-issue storm: a lever stamped at a real issue that lacked the
# `<!-- lever:… -->` marker was invisible to the marker-scan, so every `--apply` minted a fresh
# marked duplicate and repointed the lever at it. The fix: recover a stamped pointer via a direct
# REST lookup (issue_by_number) before minting. Hermetic — monkeypatches `sh`, hits no network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
tool="$here/../sync-hishand-issues.py"
[ -f "$tool" ] || { echo "FAIL: cannot find sync-hishand-issues.py at $tool" >&2; exit 1; }

python3 - "$tool" <<'PY'
import importlib.util, json, sys

spec = importlib.util.spec_from_file_location("synchh", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

fails = []
def check(c, msg):
    print(("ok   " if c else "FAIL ") + msg)
    if not c: fails.append(msg)

def fake_sh(args, check=True, input_text=None):
    if args[:3] == ["gh", "repo", "view"]:
        return "organvm/limen"
    if args[:2] == ["gh", "api"]:
        tail = args[-1]
        if tail.endswith("/issues/892"):   # a real issue WITHOUT our marker (the bug case)
            return json.dumps({"number": 892, "state": "open", "body": "populate — no marker here"})
        if tail.endswith("/issues/5"):      # REST returns PRs as issues
            return json.dumps({"number": 5, "state": "open", "pull_request": {"url": "x"}, "body": "a PR"})
        if tail.endswith("/issues/999999"):  # absent -> empty stdout (check=False path)
            return ""
    return ""

m.sh = fake_sh
m._SLUG = None

got = m.issue_by_number(892)
check(got is not None and got["number"] == 892 and got["state"] == "OPEN",
      "a stamped issue lacking the marker is recognised (the #892/#827 re-mint bug)")
check(m.issue_by_number(5) is None, "a PR number is rejected, never mistaken for the lever's issue")
check(m.issue_by_number(999999) is None, "an absent issue number resolves to None (no crash, no mint)")

sys.exit(1 if fails else 0)
PY

echo "sync-hishand-dedup.test.sh: passed"
