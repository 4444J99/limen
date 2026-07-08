#!/usr/bin/env bash
# ship-gate.test.sh — regression test for scripts/ship-gate.py
#
# The predicate must fail a product-facing "done" that has no reachable external
# artifact (retro findings 4 + gap-model: 101 creative asks, nothing user-reachable;
# MONETA curl=000 while every internal predicate read green), and a merged-PR url
# must NEVER satisfy it. Deterministic: a local http.server plays the live surface,
# a fixture board plays tasks.yaml — no external network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
gate="$here/../ship-gate.py"
[ -f "$gate" ] || { echo "FAIL: cannot find ship-gate.py at $gate" >&2; exit 1; }

work="$(mktemp -d)"
srv_pid=""
trap '[ -n "$srv_pid" ] && kill "$srv_pid" 2>/dev/null; rm -rf "$work"' EXIT

# A live artifact: local static server with a rail-carrying file. Free port derived
# per-run (a pinned port collides with stale servers from interrupted runs); the
# server pid is python itself (no subshell) so the trap genuinely kills it.
mkdir -p "$work/site"
echo "install page — rail: mint.4444j99.dev" > "$work/site/index.html"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$work/site" >/dev/null 2>&1 &
srv_pid=$!
for _ in $(seq 1 50); do curl -s -o /dev/null "http://127.0.0.1:$port/" && break; sleep 0.2; done

cat > "$work/surfaces-live.json" <<JSON
{"surfaces": [
  {"id": "live-page", "kind": "http_200", "url": "http://127.0.0.1:$port/", "what": "test artifact"},
  {"id": "live-rail", "kind": "http_contains", "url": "http://127.0.0.1:$port/index.html", "needle": "mint.4444j99.dev", "what": "rail present"}
]}
JSON
cat > "$work/surfaces-dark.json" <<JSON
{"surfaces": [{"id": "dark-page", "kind": "http_200", "url": "http://127.0.0.1:1/", "what": "curl-000 artifact"}]}
JSON
cat > "$work/surfaces-stripped.json" <<JSON
{"surfaces": [{"id": "stripped-rail", "kind": "http_contains", "url": "http://127.0.0.1:$port/index.html", "needle": "not-in-the-body", "what": "rail stripped"}]}
JSON

echo "case 1: reachable artifact + rail present → exit 0"
python3 "$gate" --check --no-tasks --surfaces "$work/surfaces-live.json" --stamp "$work/stamp.json" >/dev/null \
  || { echo "FAIL: live surfaces tripped the gate" >&2; exit 1; }

echo "case 2: unreachable artifact (curl 000) → exit 1"
if python3 "$gate" --check --no-tasks --surfaces "$work/surfaces-dark.json" --stamp "$work/stamp.json" >/dev/null 2>&1; then
  echo "FAIL: dark artifact passed the gate (the MONETA failure class)" >&2; exit 1
fi

echo "case 3: artifact serves but the rail is stripped → exit 1"
if python3 "$gate" --check --no-tasks --surfaces "$work/surfaces-stripped.json" --stamp "$work/stamp.json" >/dev/null 2>&1; then
  echo "FAIL: stripped rail passed the gate" >&2; exit 1
fi

echo "case 4: product-facing done task with only a merged-PR url → exit 1 (a PR is not an artifact)"
cat > "$work/board.yaml" <<YAML
version: '1'
budget:
  total: 100
  spent: 0
tasks:
- id: T-PR-ONLY
  title: shipped the thing (allegedly)
  description: d
  repo: organvm/limen
  type: code
  target_agent: any
  status: done
  priority: high
  budget_cost: 1
  labels: [product-facing]
  urls: [https://github.com/organvm/limen/pull/999]
  updated: '2099-01-01T00:00:00Z'
- id: T-ARTIFACT
  title: shipped with a live artifact
  description: d
  repo: organvm/limen
  type: code
  target_agent: any
  status: done
  priority: high
  budget_cost: 1
  labels: [product-facing]
  urls: ["http://127.0.0.1:$port/"]
  updated: '2099-01-01T00:00:00Z'
YAML
out=""
if out="$(python3 "$gate" --check --surfaces "$work/surfaces-live.json" --tasks "$work/board.yaml" --stamp "$work/stamp.json" 2>&1)"; then
  echo "FAIL: PR-only done claim passed the gate: $out" >&2; exit 1
fi
grep -q "T-PR-ONLY" <<<"$out" || { echo "FAIL: expected T-PR-ONLY flagged, got: $out" >&2; exit 1; }
grep -q "T-ARTIFACT" <<<"$out" && ! grep -q "RED.*T-ARTIFACT" <<<"$out" || true

echo "case 5: --task gates one id regardless of label filters"
python3 "$gate" --check --task T-ARTIFACT --surfaces "$work/surfaces-live.json" --tasks "$work/board.yaml" --stamp "$work/stamp.json" >/dev/null \
  || { echo "FAIL: artifact-backed task failed --task gate" >&2; exit 1; }
if python3 "$gate" --check --task T-PR-ONLY --surfaces "$work/surfaces-live.json" --tasks "$work/board.yaml" --stamp "$work/stamp.json" >/dev/null 2>&1; then
  echo "FAIL: PR-only task passed --task gate" >&2; exit 1
fi

echo "ship-gate.test: all cases pass"
