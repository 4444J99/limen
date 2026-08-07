#!/usr/bin/env bash
# live-checkout-currency.test.sh — regression test for scripts/check-live-checkout.py's receipt.
#
# The probe existed since 2026-07-29 but answered ONLY when run, needed a network ls-remote, and
# left no artifact — so between runs the answer existed nowhere and no point-of-use consumer could
# afford to ask. This test pins the half that closes that gap (F4 of the cadence-guard arc):
#
#   coherent checkout        → state=coherent, drift=0,  exit 0, receipt written
#   behind checkout          → state=drift,    drift>0,  exit 1, receipt says so
#   no checkout at the root  → state=unverifiable-here,  exit 0, receipt STILL written
#   two consecutive runs     → byte-identical receipt (no wall-clock in the body)
#   --no-receipt             → reports, writes nothing
#
# The third case is the load-bearing one: "I could not establish this" must be its OWN recorded
# state, never folded into `coherent` and never simply absent — absence and fine must not be the
# same value downstream. Deterministic + idempotent: a local bare repo stands in for origin, so
# there is no network anywhere in this test.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
probe="$here/../check-live-checkout.py"
[ -f "$probe" ] || { echo "FAIL: cannot find check-live-checkout.py at $probe" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

G=(git -c user.email=test@limen.local -c user.name=limen-test -c commit.gpgsign=false -c init.defaultBranch=main)

# ── a local bare "origin" plus a clone that plays the live checkout ────────────────────────────
"${G[@]}" init --quiet --bare "$work/origin.git"
"${G[@]}" clone --quiet "$work/origin.git" "$work/live" 2>/dev/null
cd "$work/live"
echo one > file.txt
"${G[@]}" add file.txt
"${G[@]}" commit --quiet -m "one"
"${G[@]}" push --quiet origin main 2>/dev/null
cd "$here"

receipt="$work/receipt.json"
run() { LIMEN_ROOT="$1" python3 "$probe" --receipt "$receipt" "${@:2}"; }

field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]))" "$receipt" "$1"; }

echo "case 1: coherent checkout → drift=0, exit 0, receipt written"
out="$(run "$work/live")" || { echo "FAIL: coherent checkout exited non-zero: $out" >&2; exit 1; }
grep -q "state=coherent" <<<"$out" || { echo "FAIL: expected state=coherent, got: $out" >&2; exit 1; }
[ -f "$receipt" ] || { echo "FAIL: no receipt written for a coherent checkout" >&2; exit 1; }
[ "$(field state)" = "coherent" ] || { echo "FAIL: receipt state != coherent ($(field state))" >&2; exit 1; }
[ "$(field drift)" = "0" ] || { echo "FAIL: receipt drift != 0 ($(field drift))" >&2; exit 1; }
[ "$(field schema)" = "limen.live_checkout_currency.v1" ] || { echo "FAIL: wrong receipt schema" >&2; exit 1; }

echo "case 2: two consecutive runs produce a byte-identical receipt (no wall-clock in the body)"
h1="$(shasum "$receipt" | awk '{print $1}')"
run "$work/live" >/dev/null
h2="$(shasum "$receipt" | awk '{print $1}')"
[ "$h1" = "$h2" ] || { echo "FAIL: receipt is not idempotent ($h1 != $h2) — a body timestamp crept in" >&2; exit 1; }

echo "case 3: origin moves ahead → state=drift, behind>0, exit 1"
"${G[@]}" clone --quiet "$work/origin.git" "$work/pusher" 2>/dev/null
cd "$work/pusher"
echo two > file2.txt
"${G[@]}" add file2.txt
"${G[@]}" commit --quiet -m "two"
"${G[@]}" push --quiet origin main 2>/dev/null
cd "$work/live"
"${G[@]}" fetch --quiet origin 2>/dev/null   # objects present, HEAD deliberately left behind
cd "$here"
if out="$(run "$work/live" 2>&1)"; then
  echo "FAIL: a behind checkout did NOT trip the probe: $out" >&2; exit 1
fi
grep -q "state=drift" <<<"$out" || { echo "FAIL: expected state=drift, got: $out" >&2; exit 1; }
[ "$(field state)" = "drift" ] || { echo "FAIL: receipt state != drift ($(field state))" >&2; exit 1; }
[ "$(field behind)" -ge 1 ] || { echo "FAIL: receipt behind < 1 ($(field behind))" >&2; exit 1; }

echo "case 4: no checkout at the root → unverifiable-here is RECORDED, never folded into coherent"
rm -f "$receipt"
out="$(run "$work/nowhere")" || { echo "FAIL: absent checkout should exit 0 (host fact, not drift)" >&2; exit 1; }
grep -q "state=unverifiable-here" <<<"$out" || { echo "FAIL: expected unverifiable-here, got: $out" >&2; exit 1; }
[ -f "$receipt" ] || { echo "FAIL: no receipt for the unverifiable case — absence and fine must differ" >&2; exit 1; }
[ "$(field state)" = "unverifiable-here" ] || { echo "FAIL: receipt state != unverifiable-here ($(field state))" >&2; exit 1; }

echo "case 5: --no-receipt reports but writes nothing"
rm -f "$receipt"
run "$work/live" --no-receipt >/dev/null 2>&1 || true
[ ! -f "$receipt" ] || { echo "FAIL: --no-receipt still wrote a receipt" >&2; exit 1; }

echo "live-checkout-currency.test: all cases pass"
