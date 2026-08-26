#!/usr/bin/env bash
# Regression test for the retired synchronous-waiter circuit breaker.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
waiter="$here/../await-pr.sh"
[ -f "$waiter" ] || { echo "FAIL: cannot find await-pr.sh at $waiter" >&2; exit 1; }

set +e
help_out="$(bash "$waiter" --help 2>&1)"
help_rc=$?
refusal_out="$(bash "$waiter" 7 --repo example/repo --merge 2>&1)"
refusal_rc=$?
set -e

[ "$help_rc" -eq 0 ] || { echo "FAIL: retired waiter help exited $help_rc" >&2; exit 1; }
case "$help_out" in
  *"synchronous PR waits are forbidden"*) ;;
  *) echo "FAIL: help omitted retirement" >&2; exit 1 ;;
esac
[ "$refusal_rc" -eq 64 ] || { echo "FAIL: retired waiter exited $refusal_rc instead of 64" >&2; exit 1; }
case "$refusal_out" in
  *"synchronous PR waiters are retired"*"merge-drain.py"*"never retry or poll"*) ;;
  *) echo "FAIL: refusal omitted one-shot handoff" >&2; exit 1 ;;
esac

echo "await-pr retirement regression PASSED"
