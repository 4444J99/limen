#!/usr/bin/env bash
# check-opportunity-lane.sh — the DONE-PREDICATE for the limen-side opportunity-inbound lane (PR C).
#
# Exit 0 ⟺ the lane is healthy end-to-end:
#   (a) the delta effector runs and exits 0 even when ~/Workspace/application-pipeline is absent
#       (fail-open dry run — it must never red the beat);
#   (b) class-parity — every inbound-lead class id the delta script filters on is a real protocol
#       class in the UMA checkout's core/protocols.py (SKIP+WARN when that checkout is absent, as it
#       is in CI: the sibling UMA feat/inbound-lead-protocols PR lands the classes, not this repo);
#   (c) intent-parity — inbound-ack-hire + inbound-ack-deploy exist as SAFE intents in the
#       MAIL-TIERS registry (institutio/governance/mail-tiers.yaml);
#   (d) idempotence — running the delta script twice produces byte-identical logs/opportunity-status.json
#       once the volatile generated_at stamp is excluded.
#
# This is a durable predicate (committed), not a throwaway: it is the executable definition of "the
# opportunity lane is wired", the twin of the beat's own sensor pass.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "check-opportunity-lane: FAIL — cannot cd to repo root"; exit 1; }
# Pin the effector's root to THIS checkout so the predicate is self-contained: the delta script honors
# LIMEN_ROOT (the beat reads the live root), so without this a worktree run would write/read the LIVE
# checkout's logs/opportunity-status.json and the idempotence check would race the live beat.
export LIMEN_ROOT="$ROOT"

DELTA="scripts/opportunity-review-delta.py"
STATUS_JSON="logs/opportunity-status.json"
MAIL_TIERS="institutio/governance/mail-tiers.yaml"
fail=0

note() { echo "check-opportunity-lane: $*"; }

# ── (a) fail-open dry run ────────────────────────────────────────────────────────────────────────
# The effector must exit 0 with --json even when application-pipeline is absent. We run it exactly as
# the beat's dry lane would (no --notify), asserting a clean exit AND parseable JSON on stdout.
if out="$(python3 "$DELTA" --json 2>/dev/null)"; then
  if ! printf '%s' "$out" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
    note "FAIL (a) — delta --json did not emit valid JSON"; fail=1
  else
    note "OK (a) — delta --json exits 0 and emits valid JSON (fail-open)"
  fi
else
  note "FAIL (a) — delta --json exited non-zero (must fail open even without application-pipeline)"; fail=1
fi

# ── (b) class-parity (skip+warn when UMA absent OR when the classes have not landed yet) ─────────
# The inbound-lead protocol classes are contributed by the SIBLING UMA feat/inbound-lead-protocols PR,
# not by this repo. So this cross-repo parity is ADVISORY (the check-mail-tiers E-check philosophy):
#   - UMA checkout absent (CI)                         → SKIP+WARN (nothing to compare against)
#   - checkout present, classes present                → OK (parity proven)
#   - checkout present, classes NOT yet present        → WARN (the sibling UMA PR is not merged yet)
#   - could not locate INBOUND_CLASSES in the delta    → FAIL (a real, in-our-control drift)
# A hard FAIL only on the last case avoids a cross-PR merge deadlock while still catching real drift.
UMA_ROOT="${LIMEN_UMA_ROOT:-$HOME/Workspace/universal-mail--automation}"
UMA_PROTO="$UMA_ROOT/core/protocols.py"
if [ -f "$UMA_PROTO" ]; then
  parity_out="$(python3 - "$DELTA" "$UMA_PROTO" <<'PY'
import re, sys
delta_path, proto_path = sys.argv[1], sys.argv[2]
delta = open(delta_path, encoding="utf-8").read()
# The delta script names its filter classes in a single INBOUND_CLASSES literal.
m = re.search(r"INBOUND_CLASSES\s*[:=].*?[\(\[{](.*?)[\)\]}]", delta, re.S)
if not m:
    print("DRIFT could not locate INBOUND_CLASSES in the delta script")
    sys.exit(2)  # in-our-control drift → hard fail
classes = set(re.findall(r"[\"']([a-z0-9-]+)[\"']", m.group(1)))
proto = open(proto_path, encoding="utf-8").read()
proto_classes = set(re.findall(r'"cls"\s*:\s*"([a-z0-9-]+)"', proto))
missing = sorted(c for c in classes if c not in proto_classes)
if missing:
    print(f"PENDING {missing} not yet in UMA protocols.py — the sibling UMA inbound-lead-protocols PR is not merged")
    sys.exit(1)  # cross-repo pending → advisory warn
print(f"OK {sorted(classes)} all present in UMA protocols.py")
sys.exit(0)
PY
)"; rc=$?
  case "$rc" in
    0) note "OK (b) — class-parity: ${parity_out#OK }" ;;
    1) note "WARN (b) — class-parity: ${parity_out#PENDING }" ;;
    *) note "FAIL (b) — class-parity: ${parity_out#DRIFT }"; fail=1 ;;
  esac
else
  note "SKIP (b) — UMA checkout absent ($UMA_PROTO); the sibling UMA PR lands the inbound-lead classes"
fi

# ── (c) intent-parity ────────────────────────────────────────────────────────────────────────────
if python3 - "$MAIL_TIERS" <<'PY'
import sys, yaml
reg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
intents = {i.get("id") for i in (reg.get("safe") or {}).get("intents") or [] if isinstance(i, dict)}
need = {"inbound-ack-hire", "inbound-ack-deploy"}
missing = sorted(need - intents)
if missing:
    print(f"intent-parity: FAIL — SAFE intents missing from mail-tiers.yaml: {missing}")
    sys.exit(1)
print("intent-parity: OK — inbound-ack-hire + inbound-ack-deploy declared as SAFE intents")
sys.exit(0)
PY
then :; else note "FAIL (c) — intent-parity mismatch (see above)"; fail=1; fi

# ── (d) idempotence ──────────────────────────────────────────────────────────────────────────────
# Two dry runs must leave logs/opportunity-status.json byte-identical modulo the generated_at stamp.
python3 "$DELTA" --json >/dev/null 2>&1
a="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("generated_at",None); print(json.dumps(d,sort_keys=True))' "$STATUS_JSON" 2>/dev/null)"
python3 "$DELTA" --json >/dev/null 2>&1
b="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("generated_at",None); print(json.dumps(d,sort_keys=True))' "$STATUS_JSON" 2>/dev/null)"
if [ -z "$a" ]; then
  note "FAIL (d) — $STATUS_JSON not produced/parseable after a dry run"; fail=1
elif [ "$a" = "$b" ]; then
  note "OK (d) — $STATUS_JSON idempotent across two dry runs (generated_at excluded)"
else
  note "FAIL (d) — $STATUS_JSON differs across two dry runs (non-idempotent)"; fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "check-opportunity-lane: FAIL — opportunity lane is not healthy"
  exit 1
fi
echo "check-opportunity-lane: OK — opportunity-inbound lane healthy (delta fail-open, class+intent parity, idempotent status-json)"
exit 0
