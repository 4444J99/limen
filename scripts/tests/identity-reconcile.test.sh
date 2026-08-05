#!/usr/bin/env bash
# identity-reconcile.test.sh — regression test for `identity.py reconcile` (the SINGLE-HOME rule).
#
# The registry declares identity.emails as the single owner and digital-accounts.json as a
# `referenced_by` store that may CITE an email but never re-own one. This predicate makes that rule
# executable: every accounts[].email must be a MEMBER of the owned `emails` set. It must go RED on a
# stray (an email no owner class holds — the owner is incomplete, or the store has a typo), stay GREEN
# when every citation is owned, and NEVER false-fail where it cannot see data (store absent — CI / no
# ARCA store) or has nothing to reconcile against (owned set empty — that is verify's populate gap,
# not this check's). It must also NEVER print the cited value (counts only — the store holds PII).
#
# Deterministic + hermetic: drives the REAL registry (so the live referenced_by block is exercised)
# against a temp LIMEN_WORKSPACE, never the operator's ARCA store.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
idpy="$here/../identity.py"
[ -f "$idpy" ] || { echo "FAIL: cannot find identity.py at $idpy" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
priv="$work/_life-private"
mkdir -p "$priv"

# identity.json: the single owner holds one email.
cat > "$priv/identity.json" <<'JSON'
{"emails": ["owned@example.com"], "legal_name": {"first": "A", "last": "B"}}
JSON

run() { LIMEN_WORKSPACE="$work" python3 "$idpy" reconcile; }

pass=0
LAST_OUT=""
expect() { # <label> <want_exit>
  local label="$1" want="$2" got=0 out
  out="$(run 2>&1)" || got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL $label: expected exit $want, got $got" >&2; echo "$out" >&2; exit 1
  fi
  echo "ok   $label (exit $got)"; pass=$((pass+1)); LAST_OUT="$out"
}

# GREEN: every citation is an owned email.
cat > "$priv/digital-accounts.json" <<'JSON'
{"accounts": [{"platform": "x", "email": "owned@example.com"}]}
JSON
expect "GREEN when every accounts[].email is owned" 0

# RED: a stray email no owner class holds.
cat > "$priv/digital-accounts.json" <<'JSON'
{"accounts": [{"platform": "x", "email": "owned@example.com"}, {"platform": "y", "email": "stray@secret.example"}]}
JSON
expect "RED when an accounts[].email is not owned (re-owned/divergent)" 1
case "$LAST_OUT" in
  *stray@secret.example*) echo "FAIL redaction: reconcile printed the cited value" >&2; exit 1;;
esac
case "$LAST_OUT" in
  *"not owned"*) : ;;
  *) echo "FAIL: RED output did not name the drift" >&2; exit 1;;
esac
echo "ok   RED output is redacted (count only, never the cited email)"; pass=$((pass+1))

# SKIP: no citing store present -> cannot see data -> never false-fail.
rm -f "$priv/digital-accounts.json"
expect "GREEN (skip) when the citing store is absent (CI / no ARCA store)" 0

# SKIP: owned set empty (populate gap) -> reconcile is not the check that owns that.
cat > "$priv/identity.json" <<'JSON'
{"emails": [], "legal_name": {"first": "A", "last": "B"}}
JSON
cat > "$priv/digital-accounts.json" <<'JSON'
{"accounts": [{"platform": "x", "email": "whatever@example.com"}]}
JSON
expect "GREEN (skip) when the owned set is empty (that is verify's populate gap)" 0

# Live-contract guard: the real registry must still declare the referenced_by enforcement,
# so the single-home rule can never silently revert to prose.
real_reg="$here/../../institutio/governance/personal-facts.yaml"
python3 - "$real_reg" <<'PY'
import sys, yaml
facts = (yaml.safe_load(open(sys.argv[1])) or {}).get("facts", {})
refs = facts.get("identity.emails", {}).get("referenced_by")
assert refs, "identity.emails lost its referenced_by block (single-home rule reverted to prose)"
assert any(r.get("store", "").endswith("digital-accounts.json") for r in refs), \
    "digital-accounts.json no longer declared as a referenced_by store"
PY
echo "ok   live personal-facts.yaml still declares identity.emails.referenced_by (enforcement intact)"
pass=$((pass+1))

echo "identity-reconcile.test.sh: $pass/6 cases passed"
