#!/usr/bin/env bash
# deploy-corpus-organs.sh — the ONE-TIME deploy that moves the corpus organs out of the staged
# worktree and into the LIVE daemon (the un-caged executor). After this runs once, the heartbeat
# pushes + converges every beat with NO interactive classifier in its path — forever.
#
# Run this from BYPASS/AGENTS mode (or directly in a terminal). It is idempotent + additive: re-running
# is safe. It does NOT force-push, delete refs, or merge.
#
#   bash scripts/deploy-corpus-organs.sh            # deploy + enable + restart the daemon
#   LIMEN_ENABLE_LIVE_SYNTHESIS=0 bash scripts/...  # deploy, but leave live synthesis OFF (no spend)
set -uo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"                 # the worktree's scripts/ dir (this file's home)
LIVE="${LIMEN_ROOT:-$HOME/Workspace/limen}"
ENV="$HOME/.limen.env"

echo "[deploy] source : $SRC"
echo "[deploy] live   : $LIVE/scripts"

# 1. deploy the organs into the live checkout (additive; the daemon reads from here).
for f in capture.sh corpus-converge.py corpus-view.py heartbeat-loop.sh; do
  cp "$SRC/$f" "$LIVE/scripts/$f" && echo "[deploy] ✓ $f"
done
chmod +x "$LIVE/scripts/capture.sh" "$LIVE/scripts/corpus-converge.py" "$LIVE/scripts/corpus-view.py" 2>/dev/null || true

# 2. turn on the convergence organ (gated OFF by default). Idempotent: only append if absent.
touch "$ENV"
grep -q '^LIMEN_CORPUS_CONVERGE=' "$ENV" || echo 'LIMEN_CORPUS_CONVERGE=1' >> "$ENV"
if [ "${LIMEN_ENABLE_LIVE_SYNTHESIS:-1}" = "1" ]; then
  grep -q '^LIMEN_CORPUS_CONVERGE_LIVE=' "$ENV" || echo 'LIMEN_CORPUS_CONVERGE_LIVE=1' >> "$ENV"
  grep -q '^LIMEN_CORPUS_GRAPH=' "$ENV"         || echo 'LIMEN_CORPUS_GRAPH=1' >> "$ENV"
  echo "[deploy] live synthesis + graph shots: ON (uses ANTHROPIC_API_KEY; bounded per beat)"
else
  echo "[deploy] live synthesis: left OFF (set LIMEN_CORPUS_CONVERGE_LIVE=1 in $ENV when ready)"
fi

# 3. publish the visible page immediately (no wait for the first beat).
LIMEN_ROOT="$LIVE" python3 "$LIVE/scripts/corpus-view.py" 2>&1 | tail -1 || true

# 4. restart the daemon so heartbeat-loop.sh re-reads with the new voices wired in.
launchctl kickstart -k "gui/$(id -u)/com.limen.heartbeat" && echo "[deploy] daemon restarted"

echo "[deploy] DONE. Knowledge base: http://127.0.0.1:8788/corpus.html"
echo "[deploy] The daemon now captures (off-disk) + converges his WORDS every beat, un-caged."
