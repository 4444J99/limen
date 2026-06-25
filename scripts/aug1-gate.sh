#!/usr/bin/env bash
# aug1-gate.sh — the executable predicate for Anthony's Aug-1-2026 triad goal.
#
#   exit 0  ⟺  the gate is TRUE: $10k/wk run-rate + in the EV + clean/life progress.
#
# This is the goal as a thing you can RUN (CLAUDE.md "Definition of Done") — never prose, never
# memory, never the craving. The predicate decides. It refreshes the board (scripts/aug1-view.py),
# then reads the SAME logs/aug1-view.json the board renders, so the judge and the face can never
# disagree. Today it exits non-zero, honestly. Plan: docs/AUG1-10K-GATE.md
#
# Fails toward FALSE: a missing input is an unmet gate, never a fake pass.
set -uo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${PYTHON:-python3}"

# Refresh the single computation (renders the board + writes logs/aug1-view.json). Fails open.
"$PY" "$ROOT/scripts/aug1-view.py" >/dev/null 2>&1 || true

"$PY" - "$ROOT/logs/aug1-view.json" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"aug1-gate: cannot read view ({e}) — treating as FALSE")
    sys.exit(1)
g = v.get("gate", {})
legs = g.get("legs", [])
print(f"AUG-1 GATE — {v.get('days_left','?')} days to {v.get('deadline','?')}")
for leg in legs:
    print(f"  {'✓' if leg.get('ok') else '✗'} {leg.get('label','')}  —  {leg.get('detail','')}")
if g.get("pass"):
    print("\nGATE: TRUE — $10k/wk + in the EV + life progress. The triad holds.")
    sys.exit(0)
print(f"\nGATE: FALSE — the one move that matters: {v.get('next_act','(see board)')}")
sys.exit(1)
PY
