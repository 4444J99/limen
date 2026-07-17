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

# ── Case 11: a valid repo_overrides row (declared class + why) passes ──
FIX="$work/override-ok.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["repo_overrides"] = {"organvm/example": {"class": "governed_public", "why": "judgment recorded"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 0 "drift == ∅" "case11 valid override row passes"

# ── Case 12: an override naming an undeclared class → red ──
FIX="$work/override-badclass.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["repo_overrides"] = {"organvm/example": {"class": "no_such_class", "why": "x"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "names no declared class" "case12 unknown override class reddens"

# ── Case 13: an override without a why → red (judgment must be durable) ──
FIX="$work/override-nowhy.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["repo_overrides"] = {"organvm/example": {"class": "governed_public"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "'why' is required" "case13 override missing why reddens"

# ── Case 14: publish_candidate on a public-visibility class → red ──
FIX="$work/override-pubcand.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["repo_overrides"] = {"organvm/example": {"class": "governed_public", "why": "x", "publish_candidate": True}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "publish_candidate requires a private-visibility class" "case14 publish_candidate on public class reddens"

# ── Case 15: match_facts with a non-census key → red ──
FIX="$work/badfacts.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["classes"]["governed_public"]["match_facts"] = {"is_cool": True}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "match_facts" "case15 unknown match_facts key reddens"

# ── Case 16: a malformed seo block (negative topics_min) → red ──
FIX="$work/badseo.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["classes"]["governed_public"]["seo"] = {"description": "required", "topics_min": -3}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "topics_min" "case16 malformed seo block reddens"

# ── Case 17: classify_repo precedence — override > match_facts > glob (pure function, no gh) ──
FIX="$work/classify.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["classes"] = {
    "special": {"match": [], "visibility": "private", "branch_protection": "exempt",
                 "required_checks": [], "owner": "gitvs", "note": "override-only"},
    "forks": {"match": ["**"], "match_facts": {"fork": True}, "visibility": "any",
               "branch_protection": "exempt", "required_checks": [], "owner": "gitvs", "note": "facts"},
    "governed_public": d["classes"]["governed_public"],
}
d["repo_overrides"] = {"organvm/judged": {"class": "special", "why": "judgment"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
out="$(LIMEN_GITVS_ESTATE="$FIX" python3 - <<PY
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gitvs", "$GITVS")
g = importlib.util.module_from_spec(spec); sys.modules["gitvs"] = g
spec.loader.exec_module(g)
e = g.load_estate()
print(g.classify_repo("organvm/judged", e, facts={"fork": True}))          # override wins over facts
print(g.classify_repo("organvm/somefork", e, facts={"fork": True}))       # facts win over glob
print(g.classify_repo("organvm/plain", e, facts={"fork": False}))         # glob floor
print(g.classify_repo("organvm/plain", e))                                 # factless: fact classes skipped
PY
)"
if [ "$out" = "special
forks
governed_public
governed_public" ]; then
  pass=$((pass+1))
else
  echo "  MISMATCH (case17 classify precedence): got:"; echo "$out" | sed 's/^/    /'; fail=$((fail+1))
fi

# ── Case 18: the G/K pure rungs — drift, candidate-cite, any-exempt, seo floor (no gh needed) ──
out="$(python3 - <<PY
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gitvs", "$GITVS")
g = importlib.util.module_from_spec(spec); sys.modules["gitvs"] = g
spec.loader.exec_module(g)
estate = {
    "classes": {
        "priv": {"match": [], "visibility": "private"},
        "anyc": {"match": ["**"], "match_facts": {"fork": True}, "visibility": "any"},
        "pub": {"match": ["o/**"], "visibility": "public",
                 "seo": {"description": "required", "topics_min": 2, "homepage": "required"}},
    },
    "repo_overrides": {
        "o/candidate": {"class": "pub", "why": "wave", "publish_candidate": True},
        "o/leak": {"class": "priv", "why": "vault"},
    },
}
rows = [
    {"full_name": "o/candidate", "private": True},                       # desired pub, cand -> CITE
    {"full_name": "o/leak", "private": False},                           # desired priv, public -> FAIL
    {"full_name": "o/fork", "private": True, "fork": True},              # any -> exempt
    {"full_name": "o/ok", "private": False, "description": "d", "topics_count": 3, "homepage": "h"},
    {"full_name": "o/bare", "private": False, "description": "", "topics_count": 0, "homepage": ""},
]
fails, cites = g.visibility_drift(rows, estate)
gaps = g.seo_floor_gaps(rows, estate)
print(len(fails), len(cites), len(gaps))
print("leak" in fails[0], "candidate" in cites[0])
print(gaps[0].startswith("o/bare:") and "description" in gaps[0] and "topics<2" in gaps[0] and "homepage" in gaps[0])
PY
)"
if [ "$out" = "1 1 1
True True
True" ]; then
  pass=$((pass+1))
else
  echo "  MISMATCH (case18 G/K pure rungs): got:"; echo "$out" | sed 's/^/    /'; fail=$((fail+1))
fi

# ── Case 19: a well-formed `orgs:` (ACCOUNT-layer) row passes ──
FIX="$work/orgsok.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["orgs"] = {"reserved": {
    "match": ["organvm-*"], "plan_ok": ["free"], "repos": 0,
    "owner": "gitvs", "note": "name-reservation shells",
}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 0 "drift == ∅" "case19 valid orgs row passes"

# ── Case 20: an `orgs:` row missing plan_ok / with a malformed plan_ok → red (schema discipline) ──
FIX="$work/orgsbad.yaml"; valid_estate "$FIX"
python3 - "$FIX" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
d["orgs"] = {"reserved": {"match": ["organvm-*"], "plan_ok": "free", "repos": 0, "owner": "gitvs", "note": "bad"}}
open(sys.argv[1], "w").write(yaml.safe_dump(d))
PY
expect 1 "plan_ok must be a non-empty string list" "case20 malformed orgs row reddens"

echo
if [ "$fail" -eq 0 ]; then
  echo "gitvs.test.sh: PASS ($pass checks)"
else
  echo "gitvs.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
