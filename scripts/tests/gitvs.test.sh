#!/usr/bin/env bash
# gitvs.test.sh — regression test for the GITVS parity predicate (scripts/gitvs.py doctor --parity-only).
#
# The wiring-integrity law (sensor-without-effector = defect; #881/#883) must actually BITE. This drives
# the deterministic class-H rung against drift fixtures and asserts each violation reddens the predicate,
# while the real committed estate passes. Fixtures point LIMEN_GITVS_ESTATE at a temp file so the real
# .github/workflows job universe (used to validate required_checks) and the imports still resolve.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
export LIMEN_ROOT="$ROOT" LIMEN_OFFLINE=1
GITVS="$ROOT/scripts/gitvs.py"
[ -f "$GITVS" ] || { echo "FAIL: cannot find gitvs.py at $GITVS" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pass=0; fail=0
# expect <exit-code> <grep-pattern|-> <label>  — runs doctor --parity-only against $FIX
expect() {
  local want_rc="$1" pattern="$2" label="$3" out rc
  out="$(LIMEN_GITVS_ESTATE="$FIX" python3 "$GITVS" doctor --parity-only 2>&1)"; rc=$?
  if [ "$rc" != "$want_rc" ]; then
    echo "  MISMATCH ($label): want exit $want_rc got $rc"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  if [ "$pattern" != "-" ] && ! echo "$out" | grep -q "$pattern"; then
    echo "  MISMATCH ($label): output missing /$pattern/"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  pass=$((pass+1))
}

# A minimal VALID estate — one active + one class with a real job id (pr-gate exists in .github/workflows).
valid_estate() {
  cat > "$1" <<'YAML'
schema_version: 0.1
resource_types:
  pull_request:
    identity: derived
    desired: ["mergeable_when_green"]
    observe: "scripts/_pr_scan.py::enumerate_open_prs"
    effector:
      - {kind: delegate, argv: [python3, scripts/merge-drain.py]}
    status: active
    owner: gitvs
    note: "ok"
  release:
    identity: derived
    desired: ["tagged"]
    observe: ""
    effector: []
    status: envisioned
    owner: gitvs
    note: "owed — envisioned, may be unwired"
classes:
  governed_public:
    match: ["organvm/**"]
    visibility: public
    branch_protection: required
    required_checks: ["pr-gate"]
    owner: gitvs
    note: "ok"
YAML
}

# ── Case 0: the REAL committed estate passes (drift == ∅ at the parity level) ──
FIX="$ROOT/institutio/github/estate.yaml"
expect 0 "drift == ∅" "case0 real estate passes"

# ── Case 1: a minimal valid fixture passes ──
FIX="$work/valid.yaml"; valid_estate "$FIX"
expect 0 "drift == ∅" "case1 valid fixture passes"

# ── Case 2: an ACTIVE resource type with an unwired effector → red (the wiring-integrity law) ──
FIX="$work/unwired.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["resource_types"]["release"]["status"] = "active"   # active but observe/effector empty
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "unwired" "case2 active-but-unwired reddens"

# ── Case 3: a required_check naming no real workflow job → red ──
FIX="$work/badcheck.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["classes"]["governed_public"]["required_checks"] = ["this-job-does-not-exist"]
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "names no" "case3 dead required_check reddens"

# ── Case 4: an active effector referencing a missing script → red ──
FIX="$work/missing.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["resource_types"]["pull_request"]["effector"] = [
    {"kind": "reap", "argv": ["python3", "scripts/does-not-exist.py", "--apply"]}
]
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "does not exist" "case4 missing effector script reddens"

# ── Case 5: an old scalar effector cannot smuggle static adapter policy back into the engine ──
FIX="$work/scalar.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["resource_types"]["pull_request"]["effector"] = "delegate:scripts/merge-drain.py"
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "must be a list" "case5 scalar effector reddens"

# ── Case 6: approval is declared on the adapter and derived at runtime, never by script name ──
FIX="$work/approval.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["resource_types"]["pull_request"]["effector"][0]["approval"] = {"lever": "L-TEST-APPROVAL"}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
out="$(LIMEN_GITVS_ESTATE="$FIX" python3 "$GITVS" reconcile --check 2>&1)"; rc=$?
if [ "$rc" != 0 ] || ! echo "$out" | grep -q "gated by L-TEST-APPROVAL"; then
  echo "  MISMATCH (case6 data-declared approval gates adapter)"; echo "$out" | sed 's/^/    /'; fail=$((fail+1))
else
  pass=$((pass+1))
fi

# ── Case 7: an ACTIVE ecosystem integration whose config-push script is missing → red ──
#    (the wiring-integrity law extended to the App plane — §3 integrations registry).
FIX="$work/badintegration.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["integrations"] = {"coderabbit": {
    "category": "review", "app_slug": "coderabbitai[bot]", "config_file": ".coderabbit.yaml",
    "install_scope": ["governed_public"],
    "effector": [{"kind": "delegate", "argv": ["python3", "scripts/does-not-exist.py"]}],
    "status": "active", "owner": "gitvs", "note": "active but effector script absent",
}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "does not exist" "case7 active integration missing effector reddens"

# ── Case 8: a structurally valid ENVISIONED integration passes (owed, may be unreachable) ──
FIX="$work/okintegration.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["integrations"] = {"coderabbit": {
    "category": "review", "app_slug": "coderabbitai[bot]", "config_file": ".coderabbit.yaml",
    "install_scope": ["governed_public"],
    "effector": [{"kind": "delegate", "argv": ["python3", "scripts/future-adapter.py"]}],
    "status": "envisioned", "owner": "gitvs", "note": "owed — envisioned",
}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 0 "drift == ∅" "case8 envisioned integration passes"

# ── Case 9: an integration missing a required field → red (schema discipline) ──
FIX="$work/incompleteintegration.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["integrations"] = {"coderabbit": {"category": "review", "status": "envisioned", "owner": "gitvs"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "missing" "case9 incomplete integration reddens"

# ── Case 10: integrations cannot retain the old scalar mini-language either ──
FIX="$work/scalarintegration.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["integrations"] = {"coderabbit": {
    "category": "review", "app_slug": "coderabbitai[bot]", "config_file": ".coderabbit.yaml",
    "install_scope": ["governed_public"], "effector": "delegate:scripts/future-adapter.py",
    "status": "envisioned", "owner": "gitvs", "note": "bad scalar",
}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "must be a list" "case10 scalar integration effector reddens"

echo
if [ "$fail" -eq 0 ]; then
  echo "gitvs.test.sh: PASS ($pass checks)"
else
  echo "gitvs.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
