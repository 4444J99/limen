#!/usr/bin/env bash
# open-knowledge.sh — open the AI-exports knowledge archive. One command, nothing to remember.
#
# THE DEFECT THIS CLOSES
#   The archive was built and verified alive, but nothing opened it: the operator had to know a
#   private store path and the exact `cce archive serve` flags. The engine refuses to start without
#   both root flags, so a half-remembered command fails and the archive reads as missing. This script
#   is the front door: it derives every path from the corpora registry, starts the server when it is
#   not already answering, and opens the site.
#
# WHAT OPENS
#   The static site under <archive>/site-all, served by the engine, which adds full-text search over
#   every conversation. The Obsidian vault <archive>/vault-all is opened too when Obsidian is
#   installed; its absence is not an error.
#
# NOTHING LEAVES THE MACHINE
#   The engine binds the loopback interface only, and rejects any Host header that is not
#   127.0.0.1 or localhost on its own port, so the URL printed here is the 127.0.0.1 form.
#
# IDEMPOTENT
#   A server already answering 200 on the port is reused, never started twice. A port held by
#   something that is not the archive server is refused by name instead of being killed or shared.
#
# WHY THE PYTHON IS CHOSEN, NOT ASSUMED
#   corpus_resolve reads corpora.yaml, which needs PyYAML, and the host python3 does not carry it.
#   The first python that can import yaml is used: this checkout's cli/.venv, the live checkout's
#   cli/.venv, then python3.
#
# Usage:
#   scripts/open-knowledge.sh               # start the server if needed, open the site
#   scripts/open-knowledge.sh --status      # server state, URL, archive fingerprint, latest receipt
#   scripts/open-knowledge.sh --stop        # stop the server this script started
#   scripts/open-knowledge.sh --port 8500   # use another port (default 8472)
#   scripts/open-knowledge.sh --no-open     # start and print the URL, open nothing

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

# Chosen because no other script, doc or config in this repo names it.
port=8472
show_status=0
stop_server=0
no_open=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status) show_status=1; shift ;;
    --stop) stop_server=1; shift ;;
    --no-open) no_open=1; shift ;;
    --port)
      [[ $# -ge 2 ]] || { echo "missing value for --port" >&2; exit 2; }
      port="$2"; shift 2 ;;
    -h|--help) sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
  echo "open-knowledge: --port must be a number from 1 to 65535, got '$port'" >&2
  exit 2
fi

live_checkout="$(dirname "$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$repo_root/.git")")"

python_with_yaml=""
for candidate in "$repo_root/cli/.venv/bin/python" "$live_checkout/cli/.venv/bin/python" python3; do
  if "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    python_with_yaml="$candidate"
    break
  fi
done
if [[ -z "$python_with_yaml" ]]; then
  echo "open-knowledge: no python with PyYAML found — run: uv sync --project $repo_root/cli" >&2
  exit 127
fi

# The store and the archive folder, both derived from the registry: the store entry of the
# archive-all row, and the row's own directory. Nothing here is a hard-coded path.
if ! resolved="$(
  "$python_with_yaml" - "$repo_root" <<'PY'
import sys
from pathlib import Path

sys.path.append(str(Path(sys.argv[1]) / "scripts"))
import corpus_resolve

doc = corpus_resolve.load_registry()
archive = corpus_resolve.corpus_root("archive-all", doc)
row = (doc.get("corpora") or {}).get("archive-all") or {}
store = ((doc.get("stores") or {}).get(row.get("store")) or {}).get("root")
if archive is None or not store:
    raise SystemExit(1)
print(Path(str(store)).expanduser())
print(archive)
PY
)"; then
  echo "open-knowledge: corpora.yaml does not declare the archive-all corpus with a store" >&2
  exit 2
fi
{ read -r store; read -r archive; } <<<"$resolved"

if [[ ! -f "$archive/manifest-all.json" ]]; then
  echo "the archive is not built on this host; run cce archive build — see docs/architecture/ai-exports-archive.md" >&2
  exit 2
fi

state_dir="$store/state"
log_file="$state_dir/open-knowledge-$port.log"
pid_file="$state_dir/open-knowledge-$port.pid"
url="http://127.0.0.1:$port/"
vault="$archive/vault-all"

server_answers() {
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url" 2>/dev/null || true)" == "200" ]]
}

port_is_held() {
  (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
}

recorded_pid() {
  [[ -f "$pid_file" ]] || return 1
  local pid command_line
  pid="$(<"$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  # Trust the pid only while it still names an archive server, never a recycled number.
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *"archive serve"* ]] || return 1
  printf '%s\n' "$pid"
}

if [[ "$show_status" -eq 1 ]]; then
  if server_answers; then
    pid_note=""
    if pid="$(recorded_pid)"; then pid_note=" (pid $pid)"; fi
    echo "open-knowledge: server up on port $port$pid_note"
  else
    echo "open-knowledge: server down on port $port — start it with: limen knowledge"
  fi
  echo "  url:          $url"
  "$python_with_yaml" - "$archive" "$repo_root" <<'PY'
import glob
import json
import os
import sys

archive, repo_root = sys.argv[1], sys.argv[2]
manifest = json.load(open(os.path.join(archive, "manifest-all.json"), encoding="utf-8"))
totals = manifest.get("totals") or {}
print(f"  fingerprint:  {manifest.get('source_fingerprint', 'unknown')}")
print(f"  archive:      {totals.get('conversations', 'unknown')} conversations, {totals.get('messages', 'unknown')} messages")
print(f"  vault:        {os.path.join(archive, 'vault-all')}")
# The date closes the receipt name, so the newest receipt is the last one by that suffix.
receipts = sorted(
    glob.glob(os.path.join(repo_root, "docs", "receipts", "receipt-knowledge-alive-*.json")),
    key=lambda path: os.path.basename(path).rsplit("-", 1)[-1],
)
print(f"  receipt:      {os.path.basename(receipts[-1]) if receipts else 'none yet — run check-knowledge-alive.py --live --write-receipt'}")
PY
  exit 0
fi

if [[ "$stop_server" -eq 1 ]]; then
  if ! pid="$(recorded_pid)"; then
    rm -f "$pid_file"
    if server_answers; then
      echo "open-knowledge: port $port answers but this script did not start it — nothing stopped"
    else
      echo "open-knowledge: no server of ours on port $port — nothing to stop"
    fi
    exit 0
  fi
  kill "$pid"
  deadline=$((SECONDS + 5))
  while kill -0 "$pid" 2>/dev/null; do
    (( SECONDS < deadline )) || { echo "open-knowledge: pid $pid ignored the stop request" >&2; exit 1; }
    sleep 0.2
  done
  rm -f "$pid_file"
  echo "open-knowledge: stopped the server on port $port (pid $pid)"
  exit 0
fi

if server_answers; then
  echo "open-knowledge: server already up on port $port"
elif port_is_held; then
  echo "open-knowledge: port $port is held by something that is not the archive server — pick another with --port" >&2
  exit 1
else
  if ! command -v cce >/dev/null 2>&1; then
    echo "open-knowledge: 'cce' not on PATH — install the conversation corpus engine (see docs/architecture/ai-exports-archive.md)" >&2
    exit 127
  fi
  mkdir -p "$state_dir"
  # CCE_CORPUS_STORE_ROOT points the engine at a legacy store when left set, so it is removed for
  # this command; the two root flags below are the engine's own required inputs.
  nohup env -u CCE_CORPUS_STORE_ROOT cce archive serve \
    --project-root "$store" --corpus-store-root "$store" --archive-root "$archive" --port "$port" \
    </dev/null >>"$log_file" 2>&1 &
  server_pid=$!
  disown "$server_pid" 2>/dev/null || true
  printf '%s\n' "$server_pid" >"$pid_file"

  deadline=$((SECONDS + 10))
  until server_answers; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "open-knowledge: the server exited while starting; last log lines from $log_file:" >&2
      tail -n 5 "$log_file" >&2 || true
      exit 1
    fi
    (( SECONDS < deadline )) || { echo "open-knowledge: no answer on port $port after 10 seconds; see $log_file" >&2; exit 1; }
    sleep 0.2
  done
  echo "open-knowledge: server started on port $port (pid $server_pid, log $log_file)"
fi

echo "open-knowledge: $url"

if [[ "$no_open" -eq 0 ]]; then
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    open "$url" || echo "open-knowledge: could not open the browser — visit $url" >&2
    # The vault is a bonus: opened only when Obsidian is installed, and a failure never fails the door.
    if [[ -d "$vault" ]] && open -Ra Obsidian >/dev/null 2>&1; then
      vault_link="obsidian://open?path=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$vault")"
      open "$vault_link" || echo "open-knowledge: could not open the vault in Obsidian — folder: $vault" >&2
    fi
  else
    echo "open-knowledge: not on macOS with 'open' — visit $url"
  fi
fi
exit 0
