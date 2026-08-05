#!/usr/bin/env bash
# reap-remote-branches.test.sh — safety regression for the REMOTE-branch reaper's pure classifier +
# the double-dark arming gate. A remote delete is irreversible, so the KEEP-by-default invariants
# (protected / checked-out / open-PR / not-provably-landed → keep) must never regress.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
REAPER="$ROOT/scripts/reap-remote-branches.py"
[ -f "$REAPER" ] || { echo "FAIL: cannot find reap-remote-branches.py" >&2; exit 1; }

# ── classify() purity: assert every (Facts → Verdict) safety invariant, no git/network needed. ──
python3 - "$ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("rrb", str(root / "scripts" / "reap-remote-branches.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["rrb"] = m  # register before exec so @dataclass introspection resolves the module (py3.14)
spec.loader.exec_module(m)
F, classify = m.Facts, m.classify

def facts(**kw):
    base = dict(is_ancestor=False, pr_merged_safe=False, pr_merged_raw=False,
                pr_open=False, checked_out=False, protected=False)
    base.update(kw); return F(**base)

cases = [
    # (Facts, expected action, expected reason, expected landed)  — KEEP wins over any landed proof.
    (facts(protected=True, is_ancestor=True),        "keep", "protected", False),
    (facts(checked_out=True, is_ancestor=True),      "keep", "checked-out", False),
    (facts(pr_open=True, is_ancestor=True),          "keep", "inflight", False),
    (facts(is_ancestor=True),                        "reap", "landed-ancestor", True),
    (facts(pr_merged_safe=True),                     "reap", "landed-pr-merged", True),
    (facts(pr_merged_raw=True, pr_merged_safe=False),"keep", "pr-merged-but-advanced", False),
    (facts(),                                        "keep", "livework", False),
    # protective checks dominate a merged proof (a checked-out merged branch is still in use):
    (facts(checked_out=True, pr_merged_safe=True),   "keep", "checked-out", False),
    (facts(pr_open=True, pr_merged_safe=True),       "keep", "inflight", False),
]
fail = 0
for f, act, reason, landed in cases:
    v = classify(f)
    if (v.action, v.reason, v.landed) != (act, reason, landed):
        print(f"  MISMATCH: {f} -> {v} ; want ({act},{reason},{landed})"); fail += 1
# The one quantity --apply/--check act on must be True ONLY for the two landed-and-reapable classes.
assert classify(facts(is_ancestor=True)).landed is True
assert classify(facts(protected=True, is_ancestor=True)).landed is False, "protected+landed must NOT be reapable"
if fail:
    print(f"classify: FAIL ({fail})"); sys.exit(1)
print(f"classify: PASS ({len(cases)} invariants)")

# Enumeration is deterministic and idempotent even if the ref backend repeats a row.
class RefResult:
    returncode = 0
    stdout = "origin/zeta\norigin/HEAD\norigin/alpha\norigin/zeta\norigin/alpha\n"
    stderr = ""
m._git = lambda _args: RefResult()
assert m.remote_branches() == ["alpha", "zeta"]
print("remote enumeration: PASS (sorted + deduplicated)")
PY
rc=$?
[ "$rc" = 0 ] || exit 1

# ── double-dark: --apply WITHOUT LIMEN_REMOTE_REAP_APPLY must stay DARK (never delete). ──
out="$(LIMEN_ROOT="$ROOT" LIMEN_OFFLINE=1 LIMEN_REMOTE_REAP_APPLY=0 python3 "$REAPER" --apply 2>&1)"
if echo "$out" | grep -q "staying DARK"; then
  echo "double-dark: PASS (unarmed --apply degrades to dry-run)"
else
  echo "double-dark: FAIL — unarmed --apply did not stay dark"; echo "$out" | tail -3; exit 1
fi

echo "reap-remote-branches.test.sh: PASS"
