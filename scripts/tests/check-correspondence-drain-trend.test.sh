#!/usr/bin/env bash
# check-correspondence-drain-trend.test.sh — regression test for scripts/check-correspondence-drain-trend.py
#
# The sensor judges the SLOPE of the append-only drain-trend series, not an absolute floor:
# it must trip (exit 1 with --check) exactly on sustained NON-convergence over a day-plus window
# — reply_owed rising, needs_human rising, or a HOLD draft persistently missing — and must NOT
# trip on a draining series, a flat-at-floor series, a too-fresh spike, or a cold-started series
# with too few points. Deterministic: fixture JSONL (--trend-file), span derived from the rows'
# own timestamps — no beat, no Gmail, no network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
sensor="$here/../check-correspondence-drain-trend.py"
[ -f "$sensor" ] || { echo "FAIL: cannot find check-correspondence-drain-trend.py at $sensor" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A 72h span (≥ the 24h stale gate). Each point is one ledger rebuild.
D0="2026-07-15T00:00:00Z"; D1="2026-07-16T00:00:00Z"; D2="2026-07-17T00:00:00Z"; D3="2026-07-18T00:00:00Z"
# A <24h span for the too-fresh case.
F0="2026-07-18T00:00:00Z"; F1="2026-07-18T01:00:00Z"; F2="2026-07-18T02:00:00Z"

pt() { # ledger_ts reply_owed needs_human draft_missing
  echo "{\"timestamp\": \"$1\", \"ledger_generated_at\": \"$1\", \"reply_owed\": $2, \"terminal\": $2, \"needs_human\": $3, \"draft_missing\": $4, \"fixed_point\": true}"
}

# case 1: reply_owed 20→17→14→11 over 72h → DRAINING, exit 0
{ pt "$D0" 20 2 0; pt "$D1" 17 2 0; pt "$D2" 14 2 0; pt "$D3" 11 2 0; } > "$work/draining.jsonl"
# case 2: reply_owed 11→14→17→20 over 72h → STALLED (reply_owed-rising), exit 1
{ pt "$D0" 11 2 0; pt "$D1" 14 2 0; pt "$D2" 17 2 0; pt "$D3" 20 2 0; } > "$work/rising.jsonl"
# case 3: reply_owed flat but needs_human 2→5 over 72h → STALLED (needs_human-rising), exit 1
{ pt "$D0" 12 2 0; pt "$D1" 12 3 0; pt "$D2" 12 4 0; pt "$D3" 12 5 0; } > "$work/human-rising.jsonl"
# case 4: everything flat at the irreducible floor over 72h → CONVERGED, exit 0
{ pt "$D0" 9 9 0; pt "$D1" 9 9 0; pt "$D2" 9 9 0; pt "$D3" 9 9 0; } > "$work/converged.jsonl"
# case 5: reply_owed rising but span < 24h → TOO-FRESH, exit 0
{ pt "$F0" 10 2 0; pt "$F1" 12 2 0; pt "$F2" 14 2 0; } > "$work/too-fresh.jsonl"
# case 6: only 2 points (< min-points 3) → INSUFFICIENT-HISTORY, exit 0
{ pt "$D0" 20 2 0; pt "$D3" 30 2 0; } > "$work/short.jsonl"
# case 7: reply_owed flat, needs_human flat, but draft_missing > 0 at EVERY point over 72h → STALLED, exit 1
{ pt "$D0" 9 2 1; pt "$D1" 9 2 2; pt "$D2" 9 2 1; pt "$D3" 9 2 1; } > "$work/stuck-drafts.jsonl"

gate() { python3 "$sensor" --check --trend-file "$1" --stamp "$work/stamp.json"; }

echo "case 1: draining series → exit 0, DRAINING"
out="$(gate "$work/draining.jsonl")" || { echo "FAIL: draining series tripped the gate: $out" >&2; exit 1; }
grep -q "DRAINING" <<<"$out" || { echo "FAIL: expected DRAINING, got: $out" >&2; exit 1; }

echo "case 2: rising reply_owed over 72h → exit 1, reply_owed-rising"
if out="$(gate "$work/rising.jsonl" 2>&1)"; then
  echo "FAIL: rising backlog passed the gate: $out" >&2; exit 1
fi
grep -q "reply_owed-rising" <<<"$out" || { echo "FAIL: expected reply_owed-rising, got: $out" >&2; exit 1; }

echo "case 3: rising needs_human over 72h → exit 1, needs_human-rising"
if out="$(gate "$work/human-rising.jsonl" 2>&1)"; then
  echo "FAIL: rising needs_human passed the gate: $out" >&2; exit 1
fi
grep -q "needs_human-rising" <<<"$out" || { echo "FAIL: expected needs_human-rising, got: $out" >&2; exit 1; }

echo "case 4: flat-at-floor → exit 0, CONVERGED"
out="$(gate "$work/converged.jsonl")" || { echo "FAIL: flat-at-floor tripped the gate: $out" >&2; exit 1; }
grep -q "CONVERGED" <<<"$out" || { echo "FAIL: expected CONVERGED, got: $out" >&2; exit 1; }

echo "case 5: rising but span < 24h → exit 0, TOO-FRESH"
out="$(gate "$work/too-fresh.jsonl")" || { echo "FAIL: too-fresh spike tripped the gate: $out" >&2; exit 1; }
grep -q "TOO-FRESH" <<<"$out" || { echo "FAIL: expected TOO-FRESH, got: $out" >&2; exit 1; }

echo "case 6: < min-points → exit 0, INSUFFICIENT-HISTORY"
out="$(gate "$work/short.jsonl")" || { echo "FAIL: short series tripped the gate: $out" >&2; exit 1; }
grep -q "INSUFFICIENT-HISTORY" <<<"$out" || { echo "FAIL: expected INSUFFICIENT-HISTORY, got: $out" >&2; exit 1; }

echo "case 7: persistent draft-missing over 72h → exit 1, draft-missing-persistent"
if out="$(gate "$work/stuck-drafts.jsonl" 2>&1)"; then
  echo "FAIL: persistent draft-missing passed the gate: $out" >&2; exit 1
fi
grep -q "draft-missing-persistent" <<<"$out" || { echo "FAIL: expected draft-missing-persistent, got: $out" >&2; exit 1; }

echo "case 8: missing/absent trend file → exit 0 (fail-open, insufficient-history)"
out="$(gate "$work/does-not-exist.jsonl")" || { echo "FAIL: absent series tripped the gate: $out" >&2; exit 1; }
grep -q "INSUFFICIENT-HISTORY" <<<"$out" || { echo "FAIL: expected insufficient-history on absent file, got: $out" >&2; exit 1; }

echo "case 9: stamp carries the verdict and the deltas"
gate "$work/draining.jsonl" >/dev/null
python3 - "$work/stamp.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["verdict"] == "draining", d
assert d["reply_owed_delta"] == -9, d
assert d["converging"] is True, d
assert d["schema"] == "limen.correspondence.drain-trend.v1", d
EOF

echo "check-correspondence-drain-trend.test: all cases pass"
