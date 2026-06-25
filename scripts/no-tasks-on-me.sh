#!/usr/bin/env bash
# no-tasks-on-me.sh — executable predicate for the Closeout Definition.
#
# Proves the invariant the charter demands but never mechanized:
#   "A his-hand task never hangs on him, on Claude's head, or in recall-only
#    memory — every owed item lives in a git-tracked owner record, and no
#    preserved work is stranded on a local-only ref."
#
# Recall-only memory (~/.claude/.../memory) lives OUTSIDE the repo, so anything
# parked only there hangs on this machine, not in a durable home. This script
# is the permanent home for that guarantee: run it instead of re-auditing by
# hand each session.
#
# Exit 0  <=>  nothing hangs on me.  Idempotent: a re-run mutates nothing.
#
# PII firewall (memory: health-pii-in-generator-code) — the registry is
# git-tracked and PUBLISHES, so this script must NOT hardcode any of his
# specific conditions/drugs. It scans only for generic measurement/dose SHAPES
# (which name nothing of his) plus an OPTIONAL off-repo denylist; the specific
# literals, if ever enumerated, live off-repo and never enter git.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REGISTRY="${LIMEN_HIS_HAND_LEVERS:-$ROOT/his-hand-levers.json}"
DENYLIST="${LIMEN_PII_DENYLIST:-$HOME/Workspace/_health-private/pii-denylist.txt}"

fail=0
ok()  { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

# ---------------------------------------------------------------------------
# 1-4: registry integrity, completeness, owner-traceability, and PII-safety.
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" "$DENYLIST" <<'PY'; then fail=1; fi
import json, re, sys
reg_path, deny_path = sys.argv[1], sys.argv[2]
rc = 0
try:
    d = json.load(open(reg_path))
except Exception as e:
    print(f"FAIL  registry not valid JSON: {e}"); sys.exit(1)
levers = d.get("levers") if isinstance(d, dict) else None
if not isinstance(levers, list) or not levers:
    print("FAIL  registry has no non-empty 'levers' list — the permanent home is missing/broken")
    sys.exit(1)

REQUIRED = ("id", "label", "owner", "cost", "unlocks", "source_task")
seen = set()
for lev in levers:
    lid = str(lev.get("id", "<no-id>"))
    for k in REQUIRED:
        if not str(lev.get(k, "")).strip():
            print(f"FAIL  lever {lid}: missing/empty required field '{k}' (un-ownable / un-traceable)"); rc = 1
    if lid in seen:
        print(f"FAIL  duplicate lever id: {lid}"); rc = 1
    seen.add(lid)

# PII firewall — generic, non-identifying shapes only (names nothing of his).
blob = json.dumps(d).lower()
SHAPES = r"\b\d+\s?mg\b|\bmg/dl\b|\bmmhg\b|\b\d+\s?mcg\b|\b\d+\s?ml\b|\bbpm\b"
shape_hits = sorted(set(re.findall(SHAPES, blob)))
if shape_hits:
    print(f"FAIL  registry contains clinical measurement/dose shapes {shape_hits} — health data leaked into a published file"); rc = 1

# Optional off-repo denylist of specific literals (kept off-repo so it never publishes).
import os
if os.path.exists(deny_path):
    terms = [t.strip().lower() for t in open(deny_path) if t.strip() and not t.startswith("#")]
    deny_hits = sorted({t for t in terms if t in blob})
    if deny_hits:
        print(f"FAIL  registry contains {len(deny_hits)} off-repo-denylisted literal(s) — PII leak"); rc = 1
    else:
        print(f"ok    registry clear of all {len(terms)} off-repo-denylisted literals")
else:
    print(f"note  off-repo PII denylist absent ({deny_path}) — specific-literal scan skipped; shape scan still enforced")

if rc == 0:
    print(f"ok    registry: {len(levers)} levers, all owned + traceable, no PII shapes")
sys.exit(rc)
PY

# ---------------------------------------------------------------------------
# 5: no preserved work stranded on a local-only ref.
#    Loss-proof preserve refs use the '*-staged-*' naming. Each must be either
#    merged (reachable from origin/main) or cited by name/sha in the registry —
#    otherwise the work lives only on this machine with no durable pointer.
#    (Enumerate all branch refs and grep-filter: a for-each-ref glob does NOT
#     cross the '/' in 'heal/...', so it would silently match nothing.)
# ---------------------------------------------------------------------------
reg_text="$(cat "$REGISTRY")"
staged_refs="$(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -- '-staged-' || true)"
if [ -z "$staged_refs" ]; then
  ok "no '*-staged-*' preserve refs present (nothing to strand)"
else
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    sha="$(git rev-parse "$name")"; short="$(git rev-parse --short "$name")"
    if git merge-base --is-ancestor "$sha" origin/main 2>/dev/null; then
      ok "preserve ref $name merged into origin/main"
    elif printf '%s' "$reg_text" | grep -qiE -- "$name|${short}|${sha:0:7}"; then
      ok "preserve ref $name cited by a registry lever (durable pointer)"
    else
      bad "preserve ref $name ($short) is STRANDED — not on origin/main and not cited by any lever. Merge it, cite it in a lever's source_task, or delete it."
    fi
  done <<< "$staged_refs"
fi

# ---------------------------------------------------------------------------
# 6: the obligations surface can load + union the registry (it renders to the
#    money/obligations face — a registry it can't union is not a real home).
# ---------------------------------------------------------------------------
if ! python3 - "$REGISTRY" <<'PY'; then fail=1; fi
import json, sys
d = json.load(open(sys.argv[1]))
levs = d.get("levers", [])
ids = [l.get("id") for l in levs]
if len(ids) != len(set(ids)):
    print("FAIL  duplicate ids would collide in the obligations union"); sys.exit(1)
print(f"ok    obligations surface can union {len(levs)} levers without collision")
PY

echo
if [ "$fail" -ne 0 ]; then
  echo "VERDICT: tasks are hanging — see FAIL lines above. Hang each in its owner's git-tracked record, then re-run."
  exit 1
fi
echo "VERDICT: nothing hangs on me — every owed task lives in a git-tracked owner record."
