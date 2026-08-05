#!/usr/bin/env bash
# heal-convergence.test.sh — regression test for scripts/heal-convergence.py
#
# The predicate must trip exactly on CHRONIC non-convergence — ≥3 open heal PRs
# failing the SAME check for >48h (the growth-auditor #16–#22 / theoria #492…#500
# stall class the retro proved nothing detected) — and must NOT trip on young PRs,
# scattered checks, or small groups. Receipt outcome coverage must count receipts
# with/without the derived outcome field. Deterministic: fixture PRs (--prs-file),
# fixture clock (--now), fixture receipt archive — no gh, no network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
conv="$here/../heal-convergence.py"
[ -f "$conv" ] || { echo "FAIL: cannot find heal-convergence.py at $conv" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

NOW="2026-07-08T12:00:00Z"
OLD="2026-07-05T00:00:00Z"    # > 48h before NOW
YOUNG="2026-07-08T00:00:00Z"  # < 48h before NOW

cat > "$work/prs-chronic.json" <<JSON
[
 {"repo": "o/r", "number": 1, "url": "u1", "createdAt": "$OLD", "failing_checks": ["e2e"]},
 {"repo": "o/r", "number": 2, "url": "u2", "createdAt": "$OLD", "failing_checks": ["e2e", "lint"]},
 {"repo": "o/r", "number": 3, "url": "u3", "createdAt": "$OLD", "failing_checks": ["e2e"]}
]
JSON
cat > "$work/prs-young.json" <<JSON
[
 {"repo": "o/r", "number": 1, "url": "u1", "createdAt": "$YOUNG", "failing_checks": ["e2e"]},
 {"repo": "o/r", "number": 2, "url": "u2", "createdAt": "$YOUNG", "failing_checks": ["e2e"]},
 {"repo": "o/r", "number": 3, "url": "u3", "createdAt": "$YOUNG", "failing_checks": ["e2e"]}
]
JSON
cat > "$work/prs-scattered.json" <<JSON
[
 {"repo": "o/r", "number": 1, "url": "u1", "createdAt": "$OLD", "failing_checks": ["e2e"]},
 {"repo": "o/r", "number": 2, "url": "u2", "createdAt": "$OLD", "failing_checks": ["lint"]},
 {"repo": "o/x", "number": 3, "url": "u3", "createdAt": "$OLD", "failing_checks": ["e2e"]}
]
JSON

run() { python3 "$conv" --check --prs-file "$1" --now "$NOW" --receipts-dir "$work/receipts" --stamp "$work/stamp.json"; }

echo "case 1: 3 old heal PRs failing the SAME check → chronic, exit 1"
if out="$(run "$work/prs-chronic.json" 2>&1)"; then
  echo "FAIL: chronic stall passed the gate: $out" >&2; exit 1
fi
grep -q "CHRONIC o/r · check 'e2e'" <<<"$out" || { echo "FAIL: expected chronic e2e group, got: $out" >&2; exit 1; }

echo "case 2: same 3 PRs but young (<48h) → exit 0"
run "$work/prs-young.json" >/dev/null || { echo "FAIL: young PRs tripped the gate" >&2; exit 1; }

echo "case 3: 3 old PRs, scattered checks/repos → exit 0"
run "$work/prs-scattered.json" >/dev/null || { echo "FAIL: scattered failures tripped the gate" >&2; exit 1; }

echo "case 4: receipt outcome coverage counts with/without"
mkdir -p "$work/receipts/2026-07-08"
echo '{"receipt": {"task_id": "HEAL-a", "outcome": "fixed", "failing_checks": []}}' > "$work/receipts/2026-07-08/1-HEAL-a.result.json"
echo '{"receipt": {"task_id": "HEAL-b", "result": "url-only-legacy"}}' > "$work/receipts/2026-07-08/2-HEAL-b.result.json"
out="$(run "$work/prs-scattered.json")"
grep -q "receipt outcome coverage 1/2" <<<"$out" || { echo "FAIL: expected coverage 1/2, got: $out" >&2; exit 1; }

echo "case 5: stamp carries the chronic groups and coverage counts"
run "$work/prs-chronic.json" >/dev/null 2>&1 || true
python3 - "$work/stamp.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["open_heal_prs"] == 3, d
assert d["chronic"] and d["chronic"][0]["check"] == "e2e", d
assert "receipts_with_outcome" in d and "receipts_without_outcome" in d, d
EOF

echo "heal-convergence.test: all cases pass"
