#!/usr/bin/env bash
# await-pr.test.sh — regression test for scripts/await-pr.sh (the one sanctioned PR-gate waiter).
#
# The waiter must stay bounded and loud: CLEARED/FAILED/TIMEOUT/REFUSED-PAUSED verdicts map to
# distinct exit codes, CI-red and BLOCKED are terminal (never waited out), a merge-prohibiting
# pause marker refuses BEFORE the first poll, the per-PR lock admits exactly one live waiter, and
# --merge invokes gh with --squash --match-head-commit bound to merge-policy's MERGE-HEAD sha.
# Deterministic + idempotent: exit 0 ⟺ all cases pass. (2026-07-15 endless-watcher incident.)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
waiter="$here/../await-pr.sh"
[ -f "$waiter" ] || { echo "FAIL: cannot find await-pr.sh at $waiter" >&2; exit 1; }

stubdir="$(mktemp -d)"
trap 'rm -rf "$stubdir"' EXIT
SEQ="$stubdir/seq"; COUNT="$stubdir/count"; GHLOG="$stubdir/gh.log"

# --- stub merge-policy: replay one scripted verdict token per call; the last token repeats ---
cat > "$stubdir/policy" <<STUB
#!/usr/bin/env bash
n=\$(cat "$COUNT" 2>/dev/null || echo 0); n=\$((n+1)); printf '%s' "\$n" > "$COUNT"
tok=\$(sed -n "\${n}p" "$SEQ"); [ -z "\$tok" ] && tok=\$(tail -1 "$SEQ")
case "\$tok" in
  CLEARED) echo "VERDICT: CLEARED — non-deploy PR, mergeable, no failing checks."
           echo "MERGE-HEAD: deadbeefcafe (use gh pr merge --match-head-commit deadbeefcafe)"; exit 0 ;;
  HOLD)    echo "VERDICT: HOLD — 1 non-deploy check(s) still running. Merge once green."; exit 2 ;;
  CIRED)   echo "VERDICT: HOLD — 2 CI check(s) failing. Fix before merge."; exit 2 ;;
  BLOCKED) echo "VERDICT: BLOCKED — merge conflicts. Rebase, then re-run."; exit 3 ;;
  *)       echo "stub: unknown token \$tok" >&2; exit 99 ;;
esac
STUB
chmod +x "$stubdir/policy"

# --- stub gh: record argv; fail when GH_FAIL=1 ---
cat > "$stubdir/gh" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$GHLOG"
[ "\${GH_FAIL:-0}" = "1" ] && exit 1
exit 0
STUB
chmod +x "$stubdir/gh"

pass=0; fail=0
check() { # name want_exit seq_tokens [waiter args...]; captured output in $out
  local name="$1" want="$2" seq="$3" got
  shift 3
  workroot="$(mktemp -d)"                      # fresh hermetic LIMEN_ROOT per case
  printf '%s\n' $seq > "$SEQ"; rm -f "$COUNT" "$GHLOG"
  set +e
  out="$(PATH="$stubdir:$PATH" LIMEN_ROOT="$workroot" LIMEN_MERGE_POLICY_BIN="$stubdir/policy" \
    bash "$waiter" 7 --interval 1 "$@" 2>&1)"
  got=$?
  set -e
  if [ "$got" = "$want" ]; then
    printf '  ok   %-36s exit=%s\n' "$name" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-36s want=%s got=%s\n  --- output ---\n%s\n' "$name" "$want" "$got" "$out"; fail=$((fail+1))
  fi
  rm -rf "$workroot"
}

echo "await-pr.sh verdict matrix:"

check "immediate CLEARED"            0 "CLEARED"
check "HOLD,HOLD then CLEARED"       0 "HOLD HOLD CLEARED"
[ "$(cat "$COUNT")" = "3" ] || { echo "  FAIL polls should be 3, got $(cat "$COUNT")"; fail=$((fail+1)); }
check "BLOCKED is terminal FAILED"   1 "BLOCKED"
check "CI-red is terminal FAILED"    1 "CIRED"
check "perpetual HOLD times out"     2 "HOLD" --timeout 2
case "$out" in (*TIMEOUT*) : ;; (*) echo "  FAIL timeout output lacks TIMEOUT line"; fail=$((fail+1)) ;; esac
check "usage: bad PR"               64 "CLEARED" --timeout x

# --merge: gh invoked with --squash --match-head-commit bound to the MERGE-HEAD sha
check "--merge on CLEARED"           0 "CLEARED" --merge
if ! grep -q -- "pr merge 7 --squash --match-head-commit deadbeefcafe" "$GHLOG" 2>/dev/null; then
  echo "  FAIL --merge did not invoke gh pr merge --squash --match-head-commit deadbeefcafe"; fail=$((fail+1))
fi
export GH_FAIL=1
check "--merge with failing gh"      1 "CLEARED" --merge
unset GH_FAIL

# pause marker: prohibitions mentioning merge refuse BEFORE the first poll
workroot="$(mktemp -d)"; mkdir -p "$workroot/logs"
printf 'reason: operator study interval\nprohibitions: no dispatch, merge, rebase, PR mutation\n' \
  > "$workroot/logs/AUTONOMY_PAUSED"
printf 'CLEARED\n' > "$SEQ"; rm -f "$COUNT"
set +e
out="$(PATH="$stubdir:$PATH" LIMEN_ROOT="$workroot" LIMEN_MERGE_POLICY_BIN="$stubdir/policy" \
  bash "$waiter" 7 --interval 1 2>&1)"; got=$?
set -e
if [ "$got" = "3" ] && [ ! -f "$COUNT" ] && printf '%s' "$out" | grep -q "REFUSED"; then
  printf '  ok   %-36s exit=%s\n' "merge-prohibiting pause refuses" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-36s want=3+zero-polls got=%s polls=%s\n' "merge-prohibiting pause refuses" \
    "$got" "$(cat "$COUNT" 2>/dev/null || echo 0)"; fail=$((fail+1))
fi
# a pause whose prohibitions do NOT mention merge lets the waiter proceed
printf 'reason: study\nprohibitions: no dispatch\n' > "$workroot/logs/AUTONOMY_PAUSED"
rm -f "$COUNT"
set +e
out="$(PATH="$stubdir:$PATH" LIMEN_ROOT="$workroot" LIMEN_MERGE_POLICY_BIN="$stubdir/policy" \
  bash "$waiter" 7 --interval 1 2>&1)"; got=$?
set -e
if [ "$got" = "0" ]; then
  printf '  ok   %-36s exit=%s\n' "non-merge pause proceeds" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-36s want=0 got=%s\n' "non-merge pause proceeds" "$got"; fail=$((fail+1))
fi
rm -rf "$workroot"

# single-instance lock: a LIVE holder pid refuses; a DEAD holder pid is taken over
workroot="$(mktemp -d)"; mkdir -p "$workroot/logs/.await-pr-7.lock"
sleep 30 & lockpid=$!
printf '%s\n' "$lockpid" > "$workroot/logs/.await-pr-7.lock/pid"
printf 'CLEARED\n' > "$SEQ"; rm -f "$COUNT"
set +e
out="$(PATH="$stubdir:$PATH" LIMEN_ROOT="$workroot" LIMEN_MERGE_POLICY_BIN="$stubdir/policy" \
  bash "$waiter" 7 --interval 1 2>&1)"; got=$?
set -e
if [ "$got" = "4" ] && printf '%s' "$out" | grep -q "ALREADY-WATCHED"; then
  printf '  ok   %-36s exit=%s\n' "live lock holder refuses" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-36s want=4 got=%s\n' "live lock holder refuses" "$got"; fail=$((fail+1))
fi
kill "$lockpid" 2>/dev/null || true; wait "$lockpid" 2>/dev/null || true
printf '%s\n' "$lockpid" > "$workroot/logs/.await-pr-7.lock/pid"   # now a dead pid
rm -f "$COUNT"
set +e
out="$(PATH="$stubdir:$PATH" LIMEN_ROOT="$workroot" LIMEN_MERGE_POLICY_BIN="$stubdir/policy" \
  bash "$waiter" 7 --interval 1 2>&1)"; got=$?
set -e
if [ "$got" = "0" ]; then
  printf '  ok   %-36s exit=%s\n' "stale lock taken over" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-36s want=0 got=%s\n' "stale lock taken over" "$got"; fail=$((fail+1))
fi
rm -rf "$workroot"

echo
echo "passed=$pass failed=$fail"
if [ "$fail" -eq 0 ]; then
  echo "await-pr regression test PASSED"; exit 0
else
  echo "await-pr regression test FAILED"; exit 1
fi
