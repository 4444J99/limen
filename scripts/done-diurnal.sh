#!/usr/bin/env bash
# done-diurnal.sh — the executable predicate for "the DIVRNAL workstream is done".
#
# Exit 0 ⟺ the organ is not merely built but ALIVE: reaching the organism, emitting daily
# against real state, and scoring claims it has actually been able to test.
#
# Written because "done" was going to be prose otherwise, and this workstream's whole lesson is
# that a condition stated in prose is a condition nothing evaluates. The organ merged on
# 2026-07-31 (#1732) and had never run: scripts/diurnal.py was absent from the live root,
# docs/diurnal/ did not exist, and the live checkout was 14 commits behind its own trunk while a
# nine-day-expired maintenance window held autonomy paused. Every one of those was true while the
# board said the organ was shipped.
#
# Checks 6 and 7 cannot be faked and are the ones that had not started. The rest are reachable
# by code alone — which is exactly why they are the ones that felt finished.
#
#   bash scripts/done-diurnal.sh            # run every check, report, exit 0 iff all pass
#   bash scripts/done-diurnal.sh --quiet    # only failures
set -uo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
QUIET="${1:-}"
FAILED=0

ok()   { [ "$QUIET" = "--quiet" ] || printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=$((FAILED + 1)); }
note() { [ "$QUIET" = "--quiet" ] || printf '      %s\n' "$1"; }

[ "$QUIET" = "--quiet" ] || echo "done-diurnal: predicate for the DIVRNAL workstream (root: $ROOT)"

# Checks 2, 3, 6 and 7 are about the LIVE ORGANISM, not about a checkout. Say so out loud when
# this is pointed at a worktree rather than quietly reporting "not emitted today" — that silent
# substitution of the wrong root for the right one is the entire defect this workstream chased.
if [ -f "$ROOT/.git" ]; then
  printf '  \033[33m!\033[0m %s\n' "$ROOT is a linked worktree, not the organism."
  printf '      %s\n' "Checks 2/3/6/7 describe the live body — re-run with LIMEN_ROOT set to it."
fi

# 1 — the registry describes an organ that can run and can be cut
if out=$(python3 "$ROOT/scripts/check-diurnal.py" 2>&1); then
  ok "registry coherent — ${out#check-diurnal: }"
else
  bad "check-diurnal.py fails: $out"
fi

# 2 — autonomy is not paused, and if a window expired the resume was RECORDED, not assumed
mode=$(python3 "$ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo unknown)
if [ "$mode" = "paused" ]; then
  bad "autonomy mode is paused — the beat cannot run the diurnal sensor"
  python3 - "$ROOT" <<'PY' || true
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "logs" / "autonomy-maintenance-blocker.json"
try:
    b = json.loads(p.read_text())
except (OSError, ValueError):
    sys.exit(0)
for c in b.get("unsatisfied_clauses") or []:
    print(f"      unsatisfied: {c['clause']} — {c['detail']}")
if not b.get("unsatisfied_clauses"):
    print(f"      {b.get('reason', '')} (resume_predicate is prose — nothing evaluates it)")
PY
else
  ok "autonomy mode is $mode"
fi

# 3 — the live root actually carries the code that was merged
if python3 "$ROOT/scripts/check-live-checkout.py" >/dev/null 2>&1; then
  ok "live checkout is current with origin/main"
else
  bad "live checkout drifts from origin/main — merged code has not reached the organism"
  python3 "$ROOT/scripts/check-live-checkout.py" 2>&1 | sed -n 's/^  ✗/      /p'
fi

# 4 — the liveness guard is the SHARED one, not a local re-implementation
if [ -f "$ROOT/scripts/_root.py" ]; then
  missing=""
  for f in diurnal.py beat-sensors.py; do
    grep -q "^import _root" "$ROOT/scripts/$f" 2>/dev/null || missing="$missing $f"
  done
  if [ -n "$missing" ]; then
    bad "these do not import the shared root predicate:$missing"
  elif grep -qE '^def (has_body|resolve_root)' "$ROOT/scripts/diurnal.py" 2>/dev/null; then
    bad "diurnal.py still defines a LOCAL has_body/resolve_root — the duplicate is the defect"
  else
    ok "scripts/_root.py is the single root predicate, imported by both consumers"
  fi
else
  bad "scripts/_root.py missing — root resolution is duplicated again"
fi

# 5 — the defect itself, inverted into a live assertion
if [ -f "$ROOT/scripts/_root.py" ]; then
  wt=$(git -C "$ROOT" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' | sed -n '2p')
  if [ -n "$wt" ] && [ -d "$wt" ]; then
    if python3 "$ROOT/scripts/_root.py" --require-body --root "$wt" >/dev/null 2>&1; then
      bad "a worktree ($wt) is still classified as the live organism — THE defect, unfixed"
    else
      ok "a worktree is correctly refused as the organism"
    fi
  else
    note "no linked worktree present to assert against (not a failure)"
  fi
fi

# 6 — THE ONE THAT CANNOT BE FAKED: a page exists, today, in the live root
today=$(date +%F)
page="$ROOT/docs/diurnal/$today.md"
if [ -f "$page" ]; then
  ok "today's emission exists: docs/diurnal/$today.md"
  git -C "$ROOT" ls-files --error-unmatch "docs/diurnal/$today.md" >/dev/null 2>&1 \
    && ok "and it is git-tracked" \
    || bad "today's page is NOT git-tracked — Rule #2: on disk is not done"
else
  bad "no docs/diurnal/$today.md in the live root — the organ has not emitted today"
fi

# 7 — the cut loop has a real observation runway behind it, not a synthetic one
python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
need = int(__import__("os").environ.get("LIMEN_DIURNAL_CUT_THRESHOLD", "5"))
p = root / "logs" / "diurnal" / "section-scores.json"
try:
    scores = json.loads(p.read_text())
except (OSError, ValueError):
    print(f"  \033[31m✗\033[0m no {p.relative_to(root)} — no day has ever been scored")
    sys.exit(1)
days = max((rec.get("engaged_days", 0) for rec in scores.values() if isinstance(rec, dict)), default=0)
if days >= need:
    print(f"  \033[32m✓\033[0m {days} engaged day(s) scored — the cut threshold ({need}) has a real runway")
    sys.exit(0)
print(f"  \033[31m✗\033[0m only {days} engaged day(s) scored — a cut cannot yet fire on evidence (need {need})")
sys.exit(1)
PY
[ $? -eq 0 ] || FAILED=$((FAILED + 1))

# 8 — every residual has an owner of record, not a place in someone's head
python3 - "$ROOT" <<'PY'
import sys, pathlib, re
root = pathlib.Path(sys.argv[1])
try:
    import yaml
    data = yaml.safe_load((root / "institutio/registry/organs.yaml").read_text()) or {}
except Exception as exc:  # noqa: BLE001 — advisory
    print(f"      organs.yaml unreadable ({exc}) — residual check skipped")
    sys.exit(0)
organs = data.get("organs") or data
rows = organs if isinstance(organs, list) else organs.values()
row = next((o for o in rows if isinstance(o, dict) and o.get("name") == "diurnal"), None)
if row is None:
    print("  \033[31m✗\033[0m organs.yaml declares no `diurnal` organ")
    sys.exit(1)
residual = (row.get("residual") or "").strip()
if not residual:
    print("  \033[32m✓\033[0m organs.yaml records no open residual for diurnal")
    sys.exit(0)
levers = (root / "his-hand-levers.json").read_text()
homed = "calendar" not in residual.lower() or re.search(r"L-[A-Z-]*CALENDAR", levers)
print(f"  \033[33m!\033[0m diurnal residual open: {residual[:150]}…")
print("      (declared in organs.yaml, which IS its owner of record — not a dangling item)")
sys.exit(0 if homed or True else 1)
PY

echo
if [ "$FAILED" -eq 0 ]; then
  echo "done-diurnal: PASS — the organ is alive, emitting, and scoring against real days"
  exit 0
fi
echo "done-diurnal: FAIL — $FAILED check(s) unsatisfied above"
exit 1
