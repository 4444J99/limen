#!/usr/bin/env bash
# sync-marketplace-config.test.sh — safety regression for the GITVS config-push effector.
#
# A config PR touches OTHER repos, so the invariants that must never regress: (1) the DOUBLE-DARK gate
# (--apply without LIMEN_MARKETPLACE_APPLY=1 must never open a PR), (2) a missing conductor config source
# is a red (source_missing), (3) the real committed estate's active integrations all have their config
# present at the conductor root (satisfied, exit 0). Offline throughout — no network, no repos touched.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
EFF="$ROOT/scripts/sync-marketplace-config.py"
[ -f "$EFF" ] || { echo "FAIL: cannot find sync-marketplace-config.py" >&2; exit 1; }
export LIMEN_OFFLINE=1
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
pass=0; fail=0

# ── Case 1: the REAL estate — every active integration's config is present at the conductor root ──
out="$(python3 "$EFF" 2>&1)"; rc=$?
if [ "$rc" = 0 ] && echo "$out" | grep -q "source_missing=0"; then
  pass=$((pass+1)); echo "  case1 real estate satisfied: PASS"
else
  fail=$((fail+1)); echo "  case1 real estate: FAIL (rc=$rc)"; echo "$out" | sed 's/^/    /'
fi

# ── Case 2: an active integration whose config SOURCE is absent → source_missing, exit 1 ──
cat > "$work/estate.yaml" <<'YAML'
schema_version: 0.1
resource_types: {}
classes: {}
integrations:
  ghost:
    category: review
    app_slug: "ghost[bot]"
    config_file: ".this-config-does-not-exist.yaml"
    install_scope: ["conductor"]
    effector: "delegate:scripts/sync-marketplace-config.py"
    status: active
    owner: gitvs
    note: "fixture — source absent"
YAML
out="$(LIMEN_GITVS_ESTATE="$work/estate.yaml" python3 "$EFF" 2>&1)"; rc=$?
if [ "$rc" = 1 ] && echo "$out" | grep -q "source_missing=1"; then
  pass=$((pass+1)); echo "  case2 missing source reddens: PASS"
else
  fail=$((fail+1)); echo "  case2 missing source: FAIL (rc=$rc)"; echo "$out" | sed 's/^/    /'
fi

# ── Case 3: DOUBLE-DARK — --apply without LIMEN_MARKETPLACE_APPLY must stay dark (no PRs) ──
out="$(LIMEN_MARKETPLACE_APPLY=0 python3 "$EFF" --apply 2>&1)"
if echo "$out" | grep -q "staying DARK"; then
  pass=$((pass+1)); echo "  case3 double-dark holds: PASS"
else
  fail=$((fail+1)); echo "  case3 double-dark: FAIL"; echo "$out" | sed 's/^/    /'
fi

echo
if [ "$fail" -eq 0 ]; then echo "sync-marketplace-config.test.sh: PASS ($pass checks)"; else
  echo "sync-marketplace-config.test.sh: FAIL ($fail failed, $pass ok)"; exit 1; fi
