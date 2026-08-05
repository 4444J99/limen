#!/usr/bin/env bash
# funnel-integrity.sh — executable definition of "the application funnel is honest".
#
# Exit 0 ⟺ healed. Read-only and idempotent: a second run changes nothing.
#
# WHY THIS EXISTS. On 2026-08-04/05 the funnel recorded SIMULATED job applications as
# provider-CONFIRMED ones against six real employers, and separately drove an agent
# through a 27h32m retry loop whose exit condition was unreachable by construction.
# Neither failure announced itself: every stage exited 0, and the fabricated receipts
# were well-formed. Prose cannot catch that class of defect on the next pass, so the
# invariants are asserted here instead.
#
# Full incident record: docs/plans/2026-08-05-application-funnel-healing.md
#
# NOTE ON READING THIS SCRIPT'S RESULT (CLAUDE.md § Never Over-Claim Completion):
# run it BARE. `funnel-integrity.sh | tail` makes $? report tail's status, which is
# essentially always 0 — a FAIL prints and is read as green. Use ${PIPESTATUS[0]} or
# save the output and filter the saved copy.
set -uo pipefail

STATE_DIR="${LIMEN_APPLICATION_STATE_DIR:-$HOME/System/Logs}"
LEDGER="${LIMEN_DELIVERY_RECEIPTS:-$STATE_DIR/delivery-receipts.json}"
LAST_RESULT="$STATE_DIR/funnel-last-result.json"
PY="${LIMEN_PY:-python3}"

fail=0
pass() { printf '  PASS  %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fail=1; }
skip() { printf '  SKIP  %s\n' "$1"; }

echo "funnel-integrity — application funnel honesty predicate"
echo

# ---------------------------------------------------------------------------
# 1. No fabricated confirmations in the live delivery ledger.
#
# The 2026-08-05 receipts carried provider_response "simulated submission accepted
# (greenhouse)" with state "confirmed", and confirmation_evidence ["portal:<entry-id>"]
# — the entry's own id, which is self-referential and proves nothing about delivery.
# ---------------------------------------------------------------------------
echo "[1] delivery ledger carries no fabricated confirmation"
if [ ! -f "$LEDGER" ]; then
  skip "no ledger at $LEDGER (nothing claimed)"
else
  ledger_report=$("$PY" - "$LEDGER" <<'PYEOF'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    doc = json.loads(path.read_text())
except ValueError:
    print("FAIL ledger is not valid JSON")
    raise SystemExit(0)
rows = doc.get("receipts", doc) if isinstance(doc, dict) else doc
if not isinstance(rows, list):
    print("FAIL ledger has no receipts list")
    raise SystemExit(0)

problems = []
for row in rows:
    if not isinstance(row, dict) or row.get("state") != "confirmed":
        continue
    rid = row.get("receipt_id") or row.get("obligation_id") or row.get("exact_target") or "<row>"
    response = str(row.get("provider_response") or "").lower()
    if "simulat" in response or "dry-run" in response or "dry run" in response:
        problems.append(f"{rid}: confirmed on a simulated provider_response")
    target = str(row.get("exact_target") or "")
    if "example.com" in target or "example.org" in target:
        problems.append(f"{rid}: confirmed against a placeholder target")
    evidence = row.get("confirmation_evidence") or row.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    if not evidence and not str(row.get("provider_id") or "").strip():
        problems.append(f"{rid}: confirmed with no evidence and no provider_id")
    # Self-referential evidence: "portal:<x>" where <x> is this row's own entry id.
    own = str(row.get("obligation_id") or "").rsplit(":", 1)[-1]
    if own:
        for item in evidence:
            if isinstance(item, str) and item.strip().lower() == f"portal:{own}".lower():
                problems.append(f"{rid}: evidence is the entry's own id, not provider evidence")

print(f"OK {len(rows)} row(s), no fabricated confirmation" if not problems else "")
for problem in problems:
    print(f"FAIL {problem}")
PYEOF
)
  if printf '%s' "$ledger_report" | grep -q '^FAIL '; then
    while IFS= read -r line; do
      [ -n "$line" ] && bad "${line#FAIL }"
    done <<< "$(printf '%s' "$ledger_report" | grep '^FAIL ')"
  else
    pass "$(printf '%s' "$ledger_report" | sed -n 's/^OK //p')"
  fi
fi
echo

# ---------------------------------------------------------------------------
# 2. Funnel state is readable, or genuinely absent — never silently corrupt.
#
# funnel-last-result.json held the literal five-byte string `test`; every read
# swallowed the parse error and reported an all-zero summary as if no cycle had run.
# ---------------------------------------------------------------------------
echo "[2] funnel state file is absent or valid"
if [ ! -f "$LAST_RESULT" ]; then
  pass "no last-cycle result yet (absent is a legitimate state)"
elif "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); raise SystemExit(0 if isinstance(d,dict) else 1)' "$LAST_RESULT" 2>/dev/null; then
  pass "last-cycle result parses as a JSON object"
else
  bad "$LAST_RESULT is unreadable — a corrupt state file reads as a true zero"
fi
echo

# ---------------------------------------------------------------------------
# 3. The application-pipeline checkout is not parked behind main.
#
# THE ROOT CAUSE. Every fabricated record in the incident traces to a live checkout
# five commits behind origin/main, where a correct implementation already existed.
# ---------------------------------------------------------------------------
echo "[3] application-pipeline checkout rests on main"
PIPELINE=""
for candidate in "${APPLICATION_PIPELINE:-}" "$HOME/Workspace/application-pipeline" \
                 "$HOME/Workspace/4444J99/application-pipeline" \
                 "$HOME/Workspace/organvm/application-pipeline" "$HOME/application-pipeline"; do
  [ -n "$candidate" ] && [ -d "$candidate/.git" ] && { PIPELINE="$candidate"; break; }
done
if [ -z "$PIPELINE" ]; then
  skip "no application-pipeline checkout found"
else
  branch=$(git -C "$PIPELINE" branch --show-current 2>/dev/null || echo "")
  if [ "$branch" != "main" ]; then
    bad "checkout is parked on '$branch', not main — this is how the 2026-08-05 fabrication happened"
  else
    behind=$(git -C "$PIPELINE" rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
    if [ "$behind" = "0" ]; then
      pass "on main, level with origin/main"
    else
      bad "on main but $behind commit(s) behind origin/main — work here rebuilds fixes that already exist"
    fi
  fi
fi
echo

# ---------------------------------------------------------------------------
# 4. No pipeline entry claims submission on self-referential evidence.
# ---------------------------------------------------------------------------
echo "[4] no pipeline entry confirmed by its own id"
if [ -z "$PIPELINE" ] || [ ! -d "$PIPELINE/pipeline" ]; then
  skip "no pipeline directory to audit"
else
  entry_report=$("${LIMEN_PIPELINE_PY:-$PIPELINE/.venv/bin/python}" - "$PIPELINE" <<'PYEOF' 2>/dev/null || echo "SKIP no usable interpreter"
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("SKIP pyyaml unavailable")
    raise SystemExit(0)

root = Path(sys.argv[1]) / "pipeline"
bad_rows, claims = [], 0
for path in root.rglob("*.yaml"):
    if path.name.startswith("_"):
        continue
    try:
        entry = yaml.safe_load(path.read_text()) or {}
    except Exception:
        continue
    if not isinstance(entry, dict):
        continue
    if str(entry.get("status", "")).lower() not in {"submitted", "confirmed"}:
        continue
    claims += 1
    eid = str(entry.get("id") or path.stem)
    evidence = (entry.get("submission") or {}).get("confirmation_evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    for item in evidence:
        if isinstance(item, str) and item.strip().lower() == f"portal:{eid}".lower():
            bad_rows.append(eid)

print(f"OK {claims} claim(s), none self-evidenced" if not bad_rows else "")
for row in bad_rows:
    print(f"FAIL {row}: confirmation_evidence is the entry's own id")
PYEOF
)
  if printf '%s' "$entry_report" | grep -q '^FAIL '; then
    while IFS= read -r line; do
      [ -n "$line" ] && bad "${line#FAIL }"
    done <<< "$(printf '%s' "$entry_report" | grep '^FAIL ')"
  elif printf '%s' "$entry_report" | grep -q '^SKIP '; then
    skip "$(printf '%s' "$entry_report" | sed -n 's/^SKIP //p')"
  else
    pass "$(printf '%s' "$entry_report" | sed -n 's/^OK //p')"
  fi
fi
echo

# ---------------------------------------------------------------------------
# 5. The daily coordinator can tell "counted zero" from "could not count".
#
# The 27-hour loop existed because it could not. An unset LIMEN_DELIVERY_RECEIPTS
# produced confirmed=0 -> shortage=3 -> blocked, on every run, forever.
# ---------------------------------------------------------------------------
echo "[5] daily coordinator distinguishes unmeasured from zero"
repo_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo ".")
if PYTHONPATH="$repo_root/cli/src" "$PY" -c '
import limen.daily_execution as d
assert hasattr(d, "_delivery_ledger_configured")
s = d._application_summary({"summary": {"qualified": 5, "staged": 4, "submitted": 4}},
                           run_id="probe", delivery_rows=[])
assert "confirmation_measured" in s
' 2>/dev/null; then
  pass "confirmation_measured is reported; an unwired ledger cannot masquerade as a shortfall"
else
  bad "daily_execution cannot distinguish an unconfigured ledger from zero confirmations"
fi
echo

if [ "$fail" -eq 0 ]; then
  echo "funnel-integrity: PASS — the funnel claims nothing it cannot evidence"
else
  echo "funnel-integrity: FAIL — see the FAIL lines above"
fi
exit "$fail"
