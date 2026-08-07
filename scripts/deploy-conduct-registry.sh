#!/usr/bin/env bash
# deploy-conduct-registry.sh — align the LIVE Worker's conduct principal registry with the
# registered source (~/.limen.env LIMEN_CONDUCT_PRINCIPAL_REGISTRY), ADDITIVELY.
#
# Why this exists (2026-08-07): the live limen-runtime Worker authenticated only the legacy
# default bearer (agent codex); every per-agent bearer in the local registry — including
# claude-direct — returned 401 because the rotated registry was never deployed as the Worker
# secret. That drift blocked the GITVS-UNCAPPED-PR-DEBT-0715 broker discharge (task targets
# agy; only a claude/agy principal or a route_to reroute can claim it, and neither bearer was
# live). Lever: L-CONDUCT-REGISTRY-DEPLOY.
#
# Additive merge: the currently-working legacy bearer (LIMEN_CONDUCT_TOKEN) is retained as
# principal codex-direct-legacy, so no live lane loses auth when the new registry lands.
# Idempotent: re-running puts the same merged document. Secrets are read from env and piped
# to wrangler; nothing is printed or written to disk.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1090
. ~/.limen.env
set +a

merged=$(python3 - <<'EOF'
import json
import os

registry = json.loads(os.environ["LIMEN_CONDUCT_PRINCIPAL_REGISTRY"])
legacy = os.environ.get("LIMEN_CONDUCT_TOKEN", "")
bearers = {p["bearer"] for p in registry["principals"]}
if legacy and legacy not in bearers:
    registry["principals"].append(
        {
            "agent": "codex",
            "bearer": legacy,
            "principal_id": "codex-direct-legacy",
            "roles": ["observer", "conductor"],
            "surface": "direct",
        }
    )
print(json.dumps(registry, separators=(",", ":")))
EOF
)
[ -n "$merged" ] || { echo "deploy-conduct-registry: FAILED to build merged registry" >&2; exit 1; }

printf '%s' "$merged" | npx --prefix web/worker wrangler secret put LIMEN_CONDUCT_PRINCIPAL_REGISTRY --config web/worker/wrangler.toml
echo "deploy-conduct-registry: secret deployed (additive; legacy bearer retained)"
