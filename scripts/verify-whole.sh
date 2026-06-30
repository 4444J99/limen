#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AMBIENT_PYTHONPATH="${PYTHONPATH:-}"
PYTHONPATH_VALUE="$ROOT/cli/src${AMBIENT_PYTHONPATH:+:$AMBIENT_PYTHONPATH}"
export PYTHONPATH="$PYTHONPATH_VALUE"

step() {
  printf '\n==> %s\n' "$*"
}

step "Compile Python modules and validate shell syntax"
cd "$ROOT"
python3 -m py_compile web/api/main.py cli/src/limen/*.py scripts/probe-runtime-adapter.py scripts/validate-lifecycle-adapters.py scripts/validate-task-board.py scripts/worktree-debt.py scripts/session-corpus-ledger.py scripts/prompt-lifecycle-ledger.py scripts/prompt-priority-map.py scripts/prompt-batch-review-ledger.py scripts/prompt-packet-ledger.py scripts/current-session-fanout-plan.py scripts/capability-substrate-ledger.py scripts/consolidation-gates.py scripts/network-health.py scripts/dispatch-health.py scripts/live-root-gate.py scripts/session-blockers-ledger.py scripts/session-lifecycle-pressure.py scripts/session-attack-paths.py scripts/conductor-tranche.py scripts/session-value-review.py
bash -n scripts/preflight-cloud-run.sh scripts/probe-local-runtime.sh scripts/probe-local-worker.sh scripts/verify-whole.sh scripts/merge-policy.sh scripts/tests/merge-policy.test.sh scripts/hooks/session-lifecycle-pressure.sh scripts/netmode.sh
plutil -lint container/launchd/com.user.netmeter.plist

step "Validate Cvrsvs Honorvm seed contracts"
CVRSV_SEED="${LIMEN_WORKSPACE_ROOT:-$HOME/Workspace}/organvm/cvrsvs-honorvm/seed.yaml"
if [[ -f "$CVRSV_SEED" ]]; then
  python3 organs/governance/validate-seed.py "$CVRSV_SEED" --strict-graph --quiet
fi

step "Verify the merge-policy predicate (verdict matrix regression test)"
bash scripts/tests/merge-policy.test.sh

step "Verify session orientation and lifecycle-pressure hooks"
bash scripts/done-session-orient.sh

step "Verify agent-instruction docs match the canonical task-state vocabulary"
python3 scripts/check-agent-docs.py

step "Validate task-board statuses match the canonical vocabulary"
python3 scripts/validate-task-board.py

step "Report preserved worktree lifecycle debt"
python3 scripts/worktree-debt.py

step "Parse GitHub workflow YAML"
python3 - <<'PY'
from pathlib import Path
import yaml
for path in sorted(Path(".github/workflows").glob("*.yml")) + sorted(Path(".github/workflows").glob("*.yaml")):
    with path.open() as handle:
        yaml.safe_load(handle)
    print(f"ok {path}")
PY

step "Generate static and private surface contracts"
(
  cd "$ROOT/web/app"
  npm run generate:data
  node scripts/fetch-pr-status.mjs
)

step "Validate lifecycle adapter parity"
scripts/validate-lifecycle-adapters.py

step "Validate generated JSON against portable schemas"
node scripts/validate-contract-schemas.mjs

step "Run API and CLI tests"
env -u LIMEN_API_TOKEN -u LIMEN_OWNER_TOKEN -u LIMEN_CLIENT_TOKEN \
  PYTHONPATH="$PYTHONPATH_VALUE" python3 -m pytest web/api/tests cli/tests -q

step "Probe local runtime adapter over HTTP"
PYTHONPATH="$PYTHONPATH_VALUE" scripts/probe-local-runtime.sh

step "Probe local Cloudflare Worker adapter over HTTP"
scripts/probe-local-worker.sh

step "Build static dashboard and validate exported surfaces"
(
  cd "$ROOT/web/app"
  npm run build
)

if [[ "${LIMEN_VERIFY_LIVE:-0}" == "1" ]]; then
  step "Verify live Firebase static surfaces"
  python3 - <<'PY'
import json
import re
import urllib.request

base = "https://device-streaming-067d747a.web.app"
expected = {
    "surface-manifest.json": ("public", ["public"]),
    "public-surface-manifest.json": ("public", ["public"]),
}
for name, (persona, surfaces) in expected.items():
    payload = json.loads(urllib.request.urlopen(f"{base}/{name}", timeout=20).read().decode())
    ids = [surface.get("id") for surface in payload.get("surfaces", [])]
    if payload.get("persona") != persona or ids != surfaces:
        raise SystemExit(f"{name} drifted: persona={payload.get('persona')} surfaces={ids}")

html = urllib.request.urlopen(f"{base}/qa", timeout=20).read().decode()
nav = re.search(r'<nav class="surfaceNav"[^>]*>([\s\S]*?)</nav>', html)
labels = re.findall(r'<a [^>]*>([^<]+)</a>', nav.group(1) if nav else "")
if labels != ["Internal", "QA", "Client", "Public"]:
    raise SystemExit(f"qa nav drifted: {labels}")
for needle in ("Owner token required", "Load QA"):
    if needle not in html:
        raise SystemExit(f"qa page missing {needle}")
for forbidden in ("LIMEN-015", "Propagate PR #234 completions", "dispatch_log"):
    if forbidden in html:
        raise SystemExit(f"qa page leaks {forbidden}")
client_html = urllib.request.urlopen(f"{base}/client", timeout=20).read().decode()
for needle in ("Client token required", "Load client"):
    if needle not in client_html:
        raise SystemExit(f"client page missing {needle}")
for name in ("tasks.json", "client-status.json", "internal-status.json", "qa-status.json", "owner-surface-manifest.json", "client-surface-manifest.json", "readiness.json"):
    try:
        urllib.request.urlopen(f"{base}/{name}", timeout=20)
    except Exception:
        continue
    raise SystemExit(f"private artifact is hosted: {name}")
print("Live Firebase surfaces verified")
PY

  LIVE_RUNTIME_URL="${LIMEN_WORKER_URL:-${NEXT_PUBLIC_API_URL:-}}"
  if [[ -n "$LIVE_RUNTIME_URL" && -n "${LIMEN_API_TOKEN:-}" && -n "${LIMEN_CLIENT_TOKEN:-}" ]]; then
    step "Verify live runtime adapter schemas"
    scripts/probe-runtime-adapter.py \
      --api-url "$LIVE_RUNTIME_URL" \
      --owner-token "$LIMEN_API_TOKEN" \
      --client-token "$LIMEN_CLIENT_TOKEN" \
      --task-id "${LIMEN_VERIFY_TASK_ID:-LIMEN-015}"
  elif [[ "${LIMEN_VERIFY_LIVE_RUNTIME:-0}" == "1" ]]; then
    printf 'LIMEN_VERIFY_LIVE_RUNTIME=1 requires LIMEN_WORKER_URL or NEXT_PUBLIC_API_URL, LIMEN_API_TOKEN, and LIMEN_CLIENT_TOKEN\n' >&2
    exit 1
  else
    printf 'Skipping live runtime adapter schema probe; set LIMEN_VERIFY_LIVE_RUNTIME=1 plus runtime URL and tokens to require it.\n'
  fi
fi

step "Check diff hygiene"
git diff --check

printf '\nWhole-system verification passed\n'
