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

# 2 — the beat's diurnal sensor is actually firing
#
# This used to hard-fail on `autonomy mode is paused — the beat cannot run the diurnal sensor`.
# That claim is FALSE and the organ disproved it: sensors run above the pause gate
# (heartbeat-loop.sh:343 calls run_monitoring inside the paused branch, per heal(beat) #1723), and
# on 2026-07-31 → 08-02 DIVRNAL emitted three unattended days with autonomy paused throughout.
#
# It was also the wrong shape of check. The pause is real but it has a registry owner — the live
# policy's resume_predicate is still the prose string, whose blocking clause is filed — and the
# charter's pattern for an owned item is the `!` residual this script already emits for
# organs.yaml: an item with an owner is HOMED, not dangling. Blocking this predicate on it made
# Ω unreachable for a reason that is not DIVRNAL's condition.
#
# What DIVRNAL's doneness actually requires is that the sensor FIRES, which the old check could
# not detect at all: it would have passed a green mode while the organ sat silent for a week.
# Strictly sharper, not weaker.
today=$(date +%F)
last_run=$(python3 - "$ROOT" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "logs" / "diurnal" / "state.json"
try:
    print(max((json.loads(p.read_text()).get("last_run") or {}).values(), default=""))
except (OSError, ValueError, TypeError):
    print("")
PY
)
if [ "$last_run" = "$today" ]; then
  ok "the beat's diurnal sensor fired today (last_run $last_run)"
else
  bad "the diurnal sensor has not fired today — last_run ${last_run:-never}"
  note "the sensor runs above the pause gate; silence here is the organ, not the governor"
fi

# The pause is reported, never gated on: it is owned elsewhere and re-surfacing a filed item is
# what the charter's closeout discipline forbids.
mode=$(python3 "$ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo unknown)
if [ "$mode" = "paused" ]; then
  printf '  \033[33m!\033[0m %s\n' "autonomy mode is paused — owned by the governor's resume predicate, not by this organ"
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
print("      (owner of record: logs/autonomy-policy.json + scripts/autonomy-governor.py)")
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
#
# This read `section-scores.json` for an `engaged_days` key. Nothing in the estate wrote that key —
# `grep -rn engaged_days` matched this line and nothing else — so the check was unsatisfiable, and
# the `.get(..., 0)` default made it unsatisfiable QUIETLY: it reported "0 days, not there yet",
# which is indistinguishable from an honest early runway. A KeyError would have surfaced it on day
# one. Same species as the resume_predicate written as prose one layer up.
#
# The runway is now derived from `ledger.jsonl`, which the organ already writes per phase. Counting
# evening EMISSIONS would over-count and the live data proves it: 2026-08-01 emitted an evening and
# had zero commits, so diurnal itself marked the day UNSCORED and moved no streak. An away-week
# would otherwise manufacture a runway and cut sections on no evidence — exactly what
# engaged_today()'s docstring exists to prevent. So a day counts only when it was ENGAGED.
python3 - "$ROOT" <<'PY'
import json, os, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
need = int(os.environ.get("LIMEN_DIURNAL_CUT_THRESHOLD", "5"))
p = root / "logs" / "diurnal" / "ledger.jsonl"
try:
    rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
except (OSError, ValueError):
    print(f"  \033[31m✗\033[0m no readable {p.relative_to(root)} — no day has ever been scored")
    sys.exit(1)


def engaged_by_git(day: str) -> bool:
    """Rows written before `engaged` existed carry the fact implicitly, in git.

    Re-derivation, not backfill: this is the same source and the same question engaged_today()
    asks at emission time, so an old row yields the answer the organ would have recorded.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--since", f"{day} 00:00", "--until", f"{day} 23:59", "--oneline"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


days = set()
for row in rows:
    if row.get("phase") != "evening":
        continue
    day = str(row.get("ts", ""))[:10]
    if not day:
        continue
    if row["engaged"] if "engaged" in row else engaged_by_git(day):
        days.add(day)

n = len(days)
if n >= need:
    print(f"  \033[32m✓\033[0m {n} engaged day(s) scored — the cut threshold ({need}) has a real runway")
    sys.exit(0)
print(f"  \033[31m✗\033[0m only {n} engaged day(s) scored — a cut cannot yet fire on evidence (need {need})")
sys.exit(1)
PY
[ $? -eq 0 ] || FAILED=$((FAILED + 1))

# 7b — the cut can actually REACH every section it is declared able to cut
#
# Check 7 proves the runway is real. This proves the runway points at the whole pool. `cuttable:
# true` is a declaration, and like every declaration in this workstream it is worth exactly what
# its consumer does with it — which, measured 2026-08-02, was 4 of 11:
#
#   build_claims() capped itself at a display parameter, so only the first few sections in
#   registry order were ever claimed; it skipped stale sections, so a section reading a dead
#   source could never accrue a streak (staleness was a SHIELD); and it implemented only
#   `metric_decreased`, so the two `metric_changed` sections check-diurnal.py's load-bearing
#   rule explicitly admits were structurally unclaimable.
#
# Three independent leaks, one symptom: section-scores.json held 4 keys while the registry
# declared 11 cuttable, and the cut could only ever fire at sections that were WORKING. Nothing
# reported that, because a subset looks exactly like a full set from the outside.
python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
try:
    import yaml
    sections = (yaml.safe_load((root / "institutio/governance/diurnal.yaml").read_text()) or {}).get("sections") or {}
except Exception as exc:  # noqa: BLE001 — advisory; check-diurnal.py owns registry validity
    print(f"      diurnal.yaml unreadable ({exc}) — cut-reach check skipped")
    sys.exit(0)
cuttable = {k for k, v in sections.items() if isinstance(v, dict) and v.get("cuttable")}
try:
    scored = set(json.loads((root / "logs/diurnal/section-scores.json").read_text()))
except (OSError, ValueError):
    scored = set()
if not scored:
    print("      no section has been scored yet — check 7 above owns that; nothing to compare")
    sys.exit(0)
missing = sorted(cuttable - scored)
if missing:
    print(f"  \033[31m✗\033[0m the cut reaches {len(cuttable & scored)}/{len(cuttable)} cuttable sections")
    print(f"      never scored, so never cuttable in practice: {', '.join(missing)}")
    sys.exit(1)
print(f"  \033[32m✓\033[0m every cuttable section is scored — the cut pool is the whole {len(cuttable)}, not a subset")
sys.exit(0)
PY
[ $? -eq 0 ] || FAILED=$((FAILED + 1))

# 7c — a proposal the organ raised is DATED, and cannot sit unanswered forever
#
# The evening has always been able to say "retire or repair this dead producer." Until the
# proposal book existed, saying it was ALL that ever happened: apply_cuts() built the list, the
# page printed it, nothing read it back. Measured 2026-08-02, the organ had printed the same
# three proposals on every evening page since 2026-07-31 while their sources aged to 10, 22 and
# 36 days — narration, not a loop.
#
# This does NOT give the organ deletion authority. "Retire or repair" is a judgment it cannot
# make, and the retire-PR stays a hand step owned by organs.yaml's declared residual. What
# changes is that the judgment is now owed on a clock and a red check is what owes it. Setting
# `disposition` on a row in logs/diurnal/proposals.json answers one; a proposal that stops
# recurring resolves itself, so this can never stay red on a condition already fixed.
python3 - "$ROOT" <<'PY'
import datetime, json, os, pathlib, sys
root = pathlib.Path(sys.argv[1])
limit = int(os.environ.get("LIMEN_DIURNAL_PROPOSAL_MAX_AGE_DAYS", "14"))
try:
    book = json.loads((root / "logs/diurnal/proposals.json").read_text())
except (OSError, ValueError):
    print("      no proposal book yet — the evening writes it on the first engaged day")
    sys.exit(0)
today = datetime.date.today()
stale = []
for what, rec in sorted(book.items()):
    if not isinstance(rec, dict) or rec.get("disposition") is not None:
        continue
    try:
        age = (today - datetime.date.fromisoformat(str(rec.get("first_seen")))).days
    except ValueError:
        continue
    if age > limit:
        stale.append((age, what))
if stale:
    print(f"  \033[31m✗\033[0m {len(stale)} proposal(s) undisposed past {limit} days")
    for age, what in sorted(stale, reverse=True):
        print(f"      {age:>3}d  {what}")
    print("      answer one by setting `disposition` in logs/diurnal/proposals.json, or land the PR")
    sys.exit(1)
open_n = sum(1 for r in book.values() if isinstance(r, dict) and r.get("disposition") is None)
print(f"  \033[32m✓\033[0m every proposal is inside its {limit}-day window ({open_n} open, {len(book)} tracked)")
sys.exit(0)
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
