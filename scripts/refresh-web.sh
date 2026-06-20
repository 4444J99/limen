#!/usr/bin/env bash
# refresh-web.sh — regenerate the web dashboard from LIVE tasks.yaml and keep it served.
# Called as a slow voice by heartbeat-loop.sh so the browser view stays current without a
# human rebuild. READ-only w.r.t. the conductor (only rebuilds web/app/out + serves it).
set -uo pipefail
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
APP="$ROOT/web/app"
PORT="${LIMEN_WEB_PORT:-8787}"
[ -d "$APP/node_modules" ] || { echo "  web: node_modules missing — skip"; exit 0; }
cd "$APP" || exit 0

with_timeout() {
  local seconds="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" "$@"
  else
    perl -e 'alarm shift; exec @ARGV' "$seconds" "$@"
  fi
}

# re-export static site from live tasks.yaml (prebuild regenerates data, postbuild validates)
if LIMEN_TASKS="$ROOT/tasks.yaml" with_timeout "${LIMEN_WEB_BUILD_TIMEOUT:-20}" \
    npm run build >"$ROOT/logs/web-refresh.log" 2>&1; then
  echo "  web: rebuilt from live tasks.yaml"
else
  echo "  web: build failed/timed out (logs/web-refresh.log) — keeping previous export"
fi

# assemble the static-first dashboard.json (portal+summary+tasks) so /internal renders
# WITHOUT a runtime (detach-safe). Local-only (written into out/, not the committed tree).
python3 - "$APP" <<'PY' || echo "  web: dashboard.json assemble skipped"
import json, sys, pathlib
app = pathlib.Path(sys.argv[1]); g = app / ".generated" / "surfaces"
try:
    i = json.load(open(g / "internal-status.json"))
    tj = json.load(open(g / "tasks.json"))
    tasks = tj.get("tasks", tj) if isinstance(tj, dict) else tj
    summary = i.get("summary") or {}
    # inject dispatch-integrity (silent-failure + chronic detection) so the web surface
    # reaches parity with the CLI board (babysit-every-send, visualized)
    try:
        dv = json.load(open(app.parent.parent / "logs" / "dispatch-verify.json"))
        summary["integrity"] = {"counts": dv.get("counts", {}), "chronic": dv.get("chronic", [])}
    except Exception:
        pass
    out = {"portal": i.get("portal"), "summary": summary,
           "tasks": tasks if isinstance(tasks, list) else [], "storage": i.get("storage")}
    (app / "out").mkdir(exist_ok=True)
    (app / "public").mkdir(exist_ok=True)
    json.dump(out, open(app / "out" / "dashboard.json", "w"))
    json.dump(out, open(app / "public" / "dashboard.json", "w"))  # also served under `next dev` (public/)
    print(f"  web: dashboard.json ({len(out['tasks'])} tasks, per_vendor {len(out['summary'].get('per_vendor',[]))})")
except Exception as e:
    print(f"  web: dashboard.json error: {e}")
PY

# ensure the static server is up (idempotent)
if ! pgrep -f "http.server $PORT" >/dev/null 2>&1; then
  ( cd "$APP/out" && nohup python3 -m http.server "$PORT" --bind 127.0.0.1 >"$ROOT/logs/portal-web.log" 2>&1 & )
  echo "  web: server (re)started → http://127.0.0.1:$PORT/internal.html"
fi
