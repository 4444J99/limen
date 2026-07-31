#!/usr/bin/env bash
# Hermetic deny/pass matrix for scripts/hooks/outbound-preflight-guard.py.
#
# The gate's whole value is that it DENIES, so the negative cases are the deliverable — a guard
# with only happy-path tests is the "HARD BLOCK" hook in ~/.claude/settings.json, which is
# labelled a block and blocks nothing.
#
# Hermetic: a fixture registry (LIMEN_OUTBOUND_REGISTRY) whose predicates are `true` / `false`,
# and a temp receipts dir. No network, no IMAP, no real mailbox. Mirrors the fixture style of
# worktree-commit-guard.test.sh.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
HOOK="$ROOT/scripts/hooks/outbound-preflight-guard.py"
PRODUCER="$ROOT/scripts/preflight-receipt.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

cat > "$TMP/registry.yaml" <<'YAML'
schema_version: 0.1
receipts_dir: RECEIPTS_DIR
effectors:
  test.send:
    title: "fixture effector"
    match:
      - 'smtplib\.SMTP'
      - '\bscripts/mail-send\b'
    target:
      kind: email
      pattern: '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    predicate: "PREDICATE_CMD {target}"
    max_age_seconds: 900
    reason: "fixture reason"
YAML

mk_registry() {  # mk_registry <predicate-command>
  sed -e "s#RECEIPTS_DIR#$TMP/receipts#" -e "s#PREDICATE_CMD#$1#" "$TMP/registry.yaml" > "$TMP/live.yaml"
}

run_hook() {  # run_hook <command-string> -> prints hook stdout
  printf '{"tool_name":"Bash","tool_input":{"command":%s}}' \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1")" \
    | LIMEN_ROOT="$ROOT" LIMEN_OUTBOUND_REGISTRY="$TMP/live.yaml" \
      python3 "$HOOK" 2>/dev/null
}

decision() {  # decision <hook-stdout> -> "deny" | "allow"
  [ -z "$1" ] && { printf 'allow'; return; }
  printf '%s' "$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecision"])' 2>/dev/null || printf 'malformed'
}

assert_denied() { [ "$(decision "$(run_hook "$1")")" = "deny" ] && pass "$2" || fail "$2"; }
assert_passes() { [ "$(decision "$(run_hook "$1")")" = "allow" ] && pass "$2" || fail "$2"; }

echo "outbound-preflight-guard matrix"

# ── DENY: the 2026-07-31 incident, reproduced ───────────────────────────────────────────────
mk_registry true
assert_denied 'python3 -c "import smtplib; smtplib.SMTP_SSL(...)" # a@b.com' \
  "denies an SMTP send with no receipt"
assert_denied 'scripts/mail-send --to someone@example.com --subject hi' \
  "denies scripts/mail-send with no receipt"

# ── DENY: matched but no readable target ────────────────────────────────────────────────────
assert_denied 'scripts/mail-send --to "$RECIPIENT"' \
  "denies a matched send whose target is a shell variable (fail-closed inside the match)"

# ── PASS: everything unmatched ──────────────────────────────────────────────────────────────
assert_passes 'git status && ls -la' "passes an ordinary command"
assert_passes 'python3 -m pytest cli/tests -q' "passes a test run"
assert_passes 'echo "email someone@example.com about it later"' \
  "passes prose that merely mentions an address"

# ── PASS only with a FRESH, PASSING, TARGET-BOUND receipt ───────────────────────────────────
LIMEN_ROOT="$ROOT" LIMEN_OUTBOUND_REGISTRY="$TMP/live.yaml" \
  python3 "$PRODUCER" --action test.send --target someone@example.com >/dev/null 2>&1
assert_passes 'scripts/mail-send --to someone@example.com' \
  "passes once a PASS receipt for that exact target exists"

# ── DENY: anti-forgery — a receipt for one target cannot authorize another ───────────────────
assert_denied 'scripts/mail-send --to other@example.com' \
  "denies a different target despite a valid receipt for the first (predicate_digest binding)"

# ── DENY: EVERY addressee needs its own receipt, not just the first one matched ───────────────
# Live bypass found by /verify on 2026-07-31: re.search binds one target, so a proven --to
# escorted an unproven --cc straight through to a second human.
assert_denied 'scripts/mail-send --to someone@example.com --cc unproven@example.com' \
  "denies a second addressee that has no receipt, despite a valid receipt for the first"
assert_denied 'scripts/mail-send --to unproven@example.com --cc someone@example.com' \
  "denies an unproven addressee in first position too (order-independent)"

# ── PASS: an address differing only in case is the same address ───────────────────────────────
assert_passes 'scripts/mail-send --to SOMEONE@Example.COM' \
  "passes a case-variant of a receipted address (one identity, no pointless re-run)"

# ── DENY: a FAILING predicate must not open the gate ─────────────────────────────────────────
mk_registry false
LIMEN_ROOT="$ROOT" LIMEN_OUTBOUND_REGISTRY="$TMP/live.yaml" \
  python3 "$PRODUCER" --action test.send --target failing@example.com >/dev/null 2>&1
assert_denied 'scripts/mail-send --to failing@example.com' \
  "denies when the ground-truth predicate FAILED"

# ── DENY: a stale receipt must not open the gate ─────────────────────────────────────────────
mk_registry true
LIMEN_ROOT="$ROOT" LIMEN_OUTBOUND_REGISTRY="$TMP/live.yaml" \
  python3 "$PRODUCER" --action test.send --target stale@example.com >/dev/null 2>&1
python3 - "$TMP/receipts" <<'PY'
import json, sys, glob
from datetime import UTC, datetime, timedelta
for path in glob.glob(f"{sys.argv[1]}/*stale*.json") or glob.glob(f"{sys.argv[1]}/*.json"):
    payload = json.loads(open(path).read())
    payload["observed_at"] = (datetime.now(UTC) - timedelta(seconds=100_000)).isoformat()
    open(path, "w").write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
assert_denied 'scripts/mail-send --to stale@example.com' \
  "denies a receipt older than max_age_seconds"

# ── The escape hatch works (and is declared in parameters.yaml) ──────────────────────────────
hatch_out="$(printf '{"tool_name":"Bash","tool_input":{"command":"scripts/mail-send --to a@b.com"}}' \
  | LIMEN_ROOT="$ROOT" LIMEN_OUTBOUND_REGISTRY="$TMP/live.yaml" LIMEN_ALLOW_UNVERIFIED_OUTBOUND=1 \
    python3 "$HOOK" 2>/dev/null)"
[ -z "$hatch_out" ] && pass "LIMEN_ALLOW_UNVERIFIED_OUTBOUND=1 bypasses" || fail "escape hatch"
grep -q 'LIMEN_ALLOW_UNVERIFIED_OUTBOUND' "$ROOT/institutio/governance/parameters.yaml" \
  && pass "escape hatch is declared in parameters.yaml" \
  || fail "escape hatch is NOT declared in parameters.yaml (check-params.py contract)"

# ── The guard never emits an "allow" DECISION (it must not widen the permission surface) ─────
# Match a permissionDecision assigned "allow", not the word "allow" in prose — the docstring
# legitimately says "silence means allow".
if grep -qE '"permissionDecision"[[:space:]]*:[[:space:]]*"allow"' "$HOOK"; then
  fail "hook must never emit an allow decision"
else
  pass "hook never emits an allow decision"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "outbound-preflight-guard: all checks passed"
  exit 0
fi
echo "outbound-preflight-guard: $fails check(s) FAILED"
exit 1
