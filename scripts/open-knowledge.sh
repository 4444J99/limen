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
#   installed; its absence is not an error. The browser step comes after the server is ready and
#   never fails the door.
#
# NOTHING LEAVES THE MACHINE
#   The engine binds the loopback interface only, and rejects any Host header that is not
#   127.0.0.1 or localhost on its own port, so the URL printed here is the 127.0.0.1 form. Every
#   HTTP liveness probe runs `curl -q --http1.1 --noproxy '*'`, so neither a user ~/.curlrc (for
#   example --http2) nor a proxy environment can break it.
#
# IDEMPOTENT
#   A server already answering is reused, never started twice. A port held by something that is not
#   the archive server is refused by name instead of being killed or shared.
#
# IDENTITY IS PROTOCOL
#   A listener counts as the archive server only when GET <url>api/ping returns HTTP 200 whose body
#   carries "ok": true — the engine's own liveness contract, the one the site's JavaScript uses to
#   enable full-text search. A listener that answers 200 on / but not that ping is a stranger. A
#   recorded pid is trusted only while `ps` shows it running `archive serve` with --port for this
#   exact port, so a recycled pid or a pid file left by another port is ignored and never signalled.
#   Every such lookup is `ps -ww`: procps ps cuts piped output to the terminal width (80 columns
#   under TERM=dumb) unless told otherwise, which would hide `archive serve` and the port on Linux.
#
# STOP AND STATUS NEVER NEED THE BUILT ARCHIVE
#   The registry is still resolved (a registry without the archive-all row exits 2), but --stop and
#   --status are handled before the archive manifest is checked: a server started earlier can always
#   be stopped, and --status without a manifest reports the server and says the archive is not built.
#   Only the start path requires the manifest and exits 2 without it.
#
# STARTS ARE SERIALIZED PER PORT
#   The start path takes a per-port lock: mkdir of <store>/state/open-knowledge-PORT.lock, then an
#   exclusive (noclobber) write of the holder pid to its pid file, so of two writers only one owns
#   it. The lock is released on every exit path and before the browser opens, and only while its pid
#   file is absent, empty or names the releasing process. A second start finds the lock held and
#   polls every 0.2 seconds until the server answers (it then reuses it), the lock is dead (it is
#   recovered and taken), or max(15, start timeout + 5) seconds pass, 15 by default (exit 1). Two
#   concurrent starts run one engine between them; a waiter whose holder failed starts its own.
#   --stop and --status never wait on the lock.
#   A lock is dead when its pid names no process, a zombie, or a process whose command line lacks
#   open-knowledge (judged with ps, never kill -0, so a live process of another user counts as
#   alive), or when it has no usable pid and the lock directory is at least 3 seconds old (a holder
#   killed between its mkdir and its pid write; the age is the directory's own modification time).
#   Only the holder of the recovery mutex (mkdir of the lock path plus .reap) removes a dead lock,
#   after judging it dead again under the mutex; a mutex at least a minute old was left by a
#   recoverer that died and is removed by whoever finds it, so such a death delays recovery by up
#   to a minute.
#
# ERRORS THAT DO NOT WAIT
#   If the state directory cannot be created, or the lock cannot be taken because the state
#   directory is not writable (or a dead lock must be recovered there), the start exits 1 at once
#   with a message naming the directory; a server that already answers is reused instead, since it
#   needs no lock. A host without curl exits 127 before any probe, for --stop, --status and the
#   start path alike.
#   --port must be a decimal number from 1 to 65535 without leading zeros; anything else exits 2.
#
# --STOP
#   If the signal to the recorded pid fails and ps no longer lists that process, the pid file is
#   removed (only while it still names that pid) and the exit is 0 with a note; if ps still lists
#   it, the exit is 1. After a stop the pid file is removed only while it still names the stopped pid.
#
# ACCEPTED RESIDUALS (named, not fixed)
#   A --stop that lands in the fork-to-exec window of a starting engine can drop its pid file; a pid
#   file is not locked against a concurrent stop of a different start.
#
# A START THAT TIMES OUT CLEANS UP AFTER ITSELF
#   If the server does not answer within 10 seconds (override with the environment variable
#   OPEN_KNOWLEDGE_START_TIMEOUT_SECONDS, a positive integer of at most six digits), the child this
#   start launched is
#   terminated (SIGTERM, then SIGKILL after 2 seconds), its pid file is removed, and the exit is 1.
#
# STATUS BINDS THE RECEIPT TO THE LIVE ARCHIVE
#   The receipt shown is the newest docs/receipts/receipt-knowledge-alive-<16hex>-<yyyymmdd>.json
#   whose 16hex is the first 16 hex characters of sha256 of the manifest's source_fingerprint. When
#   receipts of that name shape exist but none match, --status says so and names the newest on disk
#   as stale.
#
# WHY THE PYTHON IS CHOSEN, NOT ASSUMED
#   corpus_resolve reads corpora.yaml, which needs PyYAML, and the host python3 does not carry it.
#   The first python that can import yaml is used: this checkout's cli/.venv, the live checkout's
#   cli/.venv, then python3.
#
# PORTABILITY
#   Runs unchanged under macOS system bash 3.2 and bash 5, on macOS and Linux.
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
    # The whole header comment: from line 2 to the first line that is not a comment.
    -h|--help) awk 'NR == 1 { next } /^#/ { print; next } { exit }' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

number_re='^[0-9]+$'
# At most six digits: a longer value would wrap in bash arithmetic and become a negative deadline.
timeout_re='^[1-9][0-9]{0,5}$'
port_re='^[1-9][0-9]{0,4}$'

# The pattern rules out leading zeros (octal in arithmetic) and overflow before any arithmetic runs.
if [[ ! "$port" =~ $port_re ]] || (( port > 65535 )); then
  echo "open-knowledge: --port must be a number from 1 to 65535, got '$port'" >&2
  exit 2
fi

start_timeout=10
if [[ "${OPEN_KNOWLEDGE_START_TIMEOUT_SECONDS:-}" =~ $timeout_re ]]; then
  start_timeout="$OPEN_KNOWLEDGE_START_TIMEOUT_SECONDS"
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

manifest="$archive/manifest-all.json"
state_dir="$store/state"
log_file="$state_dir/open-knowledge-$port.log"
pid_file="$state_dir/open-knowledge-$port.pid"
lock_dir="$state_dir/open-knowledge-$port.lock"
url="http://127.0.0.1:$port/"
vault="$archive/vault-all"

# Every liveness probe is a curl call, so a host without curl fails here, before any probe can
# misread "no curl" as "no server".
if ! command -v curl >/dev/null 2>&1; then
  echo "open-knowledge: curl not found on PATH; the liveness probe needs it" >&2
  exit 127
fi

# The archive server, by protocol: the engine's own liveness ping answers 200 with "ok": true.
server_answers() {
  local reply code body
  reply="$(curl -q --http1.1 --noproxy '*' -s --max-time 2 -w $'\n%{http_code}' "${url}api/ping" 2>/dev/null || true)"
  code="${reply##*$'\n'}"
  body="${reply%$'\n'*}"
  [[ "$code" == "200" ]] || return 1
  [[ "$body" == *'"ok": true'* || "$body" == *'"ok":true'* ]]
}

port_is_held() {
  (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
}

recorded_pid() {
  [[ -f "$pid_file" ]] || return 1
  local pid command_line port_re
  pid="$(<"$pid_file")"
  [[ "$pid" =~ $number_re ]] || return 1
  # Trust the pid only while it still names an archive server on THIS port, never a recycled number.
  command_line="$(ps -ww -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *"archive serve"* ]] || return 1
  port_re="(^|[[:space:]])--port(=|[[:space:]]+)${port}([[:space:]]|\$)"
  [[ "$command_line" =~ $port_re ]] || return 1
  printf '%s\n' "$pid"
}

if [[ "$show_status" -eq 1 ]]; then
  if server_answers; then
    pid_note=""
    if pid="$(recorded_pid)"; then pid_note=" (pid $pid)"; fi
    echo "open-knowledge: server up on port $port$pid_note"
    echo "  url:          $url"
  else
    echo "open-knowledge: server down on port $port — start it with: limen knowledge"
    echo "  url:          $url"
    if port_is_held; then
      echo "  note:         port $port is held by something that is not the archive server"
    fi
  fi
  if [[ ! -f "$manifest" ]]; then
    echo "  archive:      not built on this host — run cce archive build (see docs/architecture/ai-exports-archive.md)"
    exit 0
  fi
  "$python_with_yaml" - "$archive" "$repo_root" <<'PY'
import glob
import hashlib
import json
import os
import re
import sys

archive, repo_root = sys.argv[1], sys.argv[2]
manifest = json.load(open(os.path.join(archive, "manifest-all.json"), encoding="utf-8"))
totals = manifest.get("totals") or {}
fingerprint = manifest.get("source_fingerprint")
print(f"  fingerprint:  {fingerprint if fingerprint is not None else 'unknown'}")
print(f"  archive:      {totals.get('conversations', 'unknown')} conversations, {totals.get('messages', 'unknown')} messages")
print(f"  vault:        {os.path.join(archive, 'vault-all')}")

# A receipt names the fingerprint it vouched for (16 hex of its sha256) and ends in the date, so the
# newest by that suffix is the last; only a receipt for the live fingerprint counts as current.
name_re = re.compile(r"^receipt-knowledge-alive-([0-9a-f]{16})-(\d{8})\.json$")
found = []
for path in glob.glob(os.path.join(repo_root, "docs", "receipts", "receipt-knowledge-alive-*.json")):
    base = os.path.basename(path)
    hit = name_re.match(base)
    if hit:
        found.append((hit.group(2), base, hit.group(1)))
found.sort()
want = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16] if isinstance(fingerprint, str) else None
current = [item for item in found if item[2] == want]
if current:
    print(f"  receipt:      {current[-1][1]}")
elif found:
    print(
        f"  receipt:      none for the current fingerprint (newest on disk: {found[-1][1]}, stale)"
        " — run check-knowledge-alive.py --live --write-receipt"
    )
else:
    print("  receipt:      none yet — run check-knowledge-alive.py --live --write-receipt")
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
  if ! kill "$pid" 2>/dev/null; then
    # The signal failed: either the process exited since it was looked up, or it cannot be signalled.
    if [[ -n "$(ps -ww -p "$pid" -o command= 2>/dev/null || true)" ]]; then
      echo "open-knowledge: cannot signal pid $pid" >&2
      exit 1
    fi
    if [[ "$(cat "$pid_file" 2>/dev/null || true)" == "$pid" ]]; then rm -f "$pid_file"; fi
    echo "open-knowledge: the server (pid $pid) had already exited; pid file removed"
    exit 0
  fi
  deadline=$((SECONDS + 5))
  while kill -0 "$pid" 2>/dev/null; do
    (( SECONDS < deadline )) || { echo "open-knowledge: pid $pid ignored the stop request" >&2; exit 1; }
    sleep 0.2
  done
  # A new start may already have written its own pid; remove the file only while it names the one stopped.
  if [[ "$(cat "$pid_file" 2>/dev/null || true)" == "$pid" ]]; then rm -f "$pid_file"; fi
  echo "open-knowledge: stopped the server on port $port (pid $pid)"
  exit 0
fi

# Only the start path needs the built archive.
if [[ ! -f "$manifest" ]]; then
  echo "the archive is not built on this host; run cce archive build — see docs/architecture/ai-exports-archive.md" >&2
  exit 2
fi

# --- the per-port start lock -------------------------------------------------------------------

lock_held=0
reap_held=0
reap_dir="$lock_dir.reap"
# A waiting start gives up only after the holder has had its whole start timeout plus a margin.
lock_wait=$(( start_timeout + 5 > 15 ? start_timeout + 5 : 15 ))

# Release the recovery mutex if this process holds it, then the start lock only while it is still
# ours: its pid file absent, empty or naming this process. A displaced holder never deletes a lock
# that another process has taken since.
release_start_lock() {
  local owner
  if [[ "$reap_held" -eq 1 ]]; then
    reap_held=0
    rm -rf "$reap_dir"
  fi
  if [[ "$lock_held" -eq 1 ]]; then
    lock_held=0
    owner="$(cat "$lock_dir/pid" 2>/dev/null || true)"
    if [[ -z "$owner" || "$owner" == "$$" ]]; then
      rm -rf "$lock_dir"
    fi
  fi
}

# Chain onto whatever EXIT trap is already set instead of replacing it.
install_lock_exit_trap() {
  local prior="" trap_words=()
  # `trap -p EXIT` prints: trap -- 'COMMAND' EXIT (nothing when unset); eval undoes its quoting.
  eval "trap_words=($(trap -p EXIT))"
  if [[ ${#trap_words[@]} -ge 3 ]]; then prior="${trap_words[2]}"; fi
  # shellcheck disable=SC2064
  trap "release_start_lock; $prior" EXIT
}

# True when PATH exists and was last modified at least SECONDS ago. The age is read from the file
# system each time, never from when this process first looked, so a lock replaced by a fresh one
# is judged by the fresh one's age. Any error reads as not old.
path_is_older_than() {
  "$python_with_yaml" -c 'import os, sys, time
sys.exit(0 if time.time() - os.stat(sys.argv[1]).st_mtime >= float(sys.argv[2]) else 1)' "$1" "$2" 2>/dev/null
}

# Dead: the pid file names a process that is gone, a zombie, or something that is not this script
# (decided by ps, not kill -0, so a live holder owned by another user still counts as alive); or the
# lock has no usable pid and its directory is at least 3 seconds old, which is a holder killed
# between its mkdir and its pid write. A lock that no longer exists is not dead.
lock_holder_is_dead() {
  local holder command_line
  holder="$(cat "$lock_dir/pid" 2>/dev/null || true)"
  if [[ "$holder" =~ $number_re ]]; then
    command_line="$(ps -ww -p "$holder" -o command= 2>/dev/null || true)"
    [[ "$command_line" != *open-knowledge* ]]
    return
  fi
  path_is_older_than "$lock_dir" 3
}

# Returns 0 holding the lock, or 10 when the server came up while waiting (lock not held). It runs
# as `acquire_start_lock || lock_status=$?`, which turns errexit off here, so every failure is
# handled explicitly.
acquire_start_lock() {
  local deadline=$((SECONDS + lock_wait))
  if ! mkdir -p "$state_dir" 2>/dev/null; then
    # A server that answers needs no state directory to be reused; only a start that would have to
    # launch an engine fails here.
    if server_answers; then
      return 10
    fi
    echo "open-knowledge: cannot create the state directory $state_dir" >&2
    exit 1
  fi
  while :; do
    if mkdir "$lock_dir" 2>/dev/null; then
      # The pid file is created exclusively (noclobber): if a holder that stalled past its own
      # recovery writes into this directory first, it owns the lock and this start waits.
      if ( set -C; printf '%s\n' "$$" >"$lock_dir/pid" ) 2>/dev/null; then
        lock_held=1
        return 0
      fi
    elif [[ ! -d "$lock_dir" && ! -w "$state_dir" ]]; then
      # A server that answers needs no lock, so it is reused even when this directory cannot be
      # written; only a start that would have to launch an engine fails here.
      if server_answers; then
        return 10
      fi
      echo "open-knowledge: cannot take the start lock; the state directory is not writable: $state_dir" >&2
      exit 1
    fi
    if server_answers; then
      return 10
    fi
    # Only a dead lock is removed, only by the holder of the recovery mutex, and only after its
    # deadness is checked again under the mutex. A mutex a minute old was left by a dead recoverer.
    if lock_holder_is_dead; then
      if mkdir "$reap_dir" 2>/dev/null; then
        reap_held=1
        if lock_holder_is_dead; then rm -rf "$lock_dir"; fi
        reap_held=0
        rm -rf "$reap_dir"
      elif [[ ! -w "$state_dir" ]]; then
        # A dead lock cannot be recovered where nothing can be created or removed; waiting out the
        # lock bound would only blame a start that does not exist.
        echo "open-knowledge: cannot take the start lock; the state directory is not writable: $state_dir" >&2
        exit 1
      elif path_is_older_than "$reap_dir" 60; then
        rm -rf "$reap_dir"
      fi
    fi
    if (( SECONDS >= deadline )); then
      echo "open-knowledge: another start on port $port did not finish within $lock_wait seconds (lock $lock_dir)" >&2
      exit 1
    fi
    sleep 0.2
  done
}

# Stop the child this start launched: SIGTERM, then SIGKILL after 2 seconds if it is still alive.
reap_child() {
  local child="$1" waited=0
  kill "$child" 2>/dev/null || true
  while kill -0 "$child" 2>/dev/null && (( waited < 10 )); do
    sleep 0.2
    waited=$((waited + 1))
  done
  if kill -0 "$child" 2>/dev/null; then
    kill -9 "$child" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

install_lock_exit_trap
lock_status=0
acquire_start_lock || lock_status=$?

if [[ "$lock_status" -eq 10 ]] || server_answers; then
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

  deadline=$((SECONDS + start_timeout))
  until server_answers; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "open-knowledge: the server exited while starting; last log lines from $log_file:" >&2
      tail -n 5 "$log_file" >&2 || true
      exit 1
    fi
    if (( SECONDS >= deadline )); then
      reap_child "$server_pid"
      echo "open-knowledge: no answer on port $port after $start_timeout seconds; see $log_file" >&2
      exit 1
    fi
    sleep 0.2
  done
  echo "open-knowledge: server started on port $port (pid $server_pid, log $log_file)"
fi

# Ready: release the start lock before the browser step so a slow open never holds other starts.
release_start_lock

echo "open-knowledge: $url"

if [[ "$no_open" -eq 0 ]]; then
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    open "$url" || echo "open-knowledge: could not open the browser — visit $url" >&2
    # The vault is a bonus: opened only when Obsidian is installed, and a failure never fails the door.
    if [[ -d "$vault" ]] && open -Ra Obsidian >/dev/null 2>&1; then
      if vault_link="obsidian://open?path=$("$python_with_yaml" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$vault")"; then
        open "$vault_link" || echo "open-knowledge: could not open the vault in Obsidian — folder: $vault" >&2
      else
        echo "open-knowledge: could not build the Obsidian link — folder: $vault" >&2
      fi
    fi
  else
    echo "open-knowledge: not on macOS with 'open' — visit $url"
  fi
fi
exit 0
