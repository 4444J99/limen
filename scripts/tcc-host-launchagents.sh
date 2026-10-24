#!/usr/bin/env bash
# Prefix owned, unhosted LaunchAgents with `DomusAgentHost run --` so launchd jobs stop minting a
# new TCC client every time their interpreter (python/node/cloudflared/brew ruby) rotates.
#
#   bash scripts/tcc-host-launchagents.sh            # dry run: show each job's argv before/after
#   bash scripts/tcc-host-launchagents.sh --apply    # back up, rewrite, and reload loaded jobs
#
# Each original plist is copied to $BACKUP first; restore with:
#   cp "$BACKUP/<label>.plist" ~/Library/LaunchAgents/ && launchctl bootout gui/$UID/<label>; \
#   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/<label>.plist
#
# Not handled here, by design:
#   com.limen.heartbeat — digest-reviewed and generated; re-plan from Domus after #561 merges.
#   com.github.domt4.homebrew-autoupdate — hosted here as a stopgap; domus-brew-schedule activate
#     (IRF-SYS-258) replaces it with the hosted com.domus.brew-maintain after #561 merges.
set -euo pipefail

HOST="$HOME/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"
AGENTS="$HOME/Library/LaunchAgents"
BACKUP="${LIMEN_CUSTODY_STAGING_ROOT:-$HOME/Workspace/limen/.limen-private/custody-staging}/launchagent-backups/$(date -u +%Y%m%dT%H%M%SZ)"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

# ianva gateway takes its argv from the reviewed source (it also fixes the live drift onto the
# runtime path); the others have no source, so their existing argv is kept and prefixed.
GATEWAY_SOURCE="$HOME/.local/share/limen/current/source/ianva/deploy/com.ianva.gateway.plist"
LABELS=(com.limen.moneta com.limen.moneta-tunnel com.ianva.gateway com.github.domt4.homebrew-autoupdate com.limen.mat-serve)

[[ -x "$HOST" ]] || { echo "DomusAgentHost missing at $HOST" >&2; exit 1; }

argv_of() { /usr/bin/plutil -extract ProgramArguments json -o - "$1" 2>/dev/null || echo "[]"; }

hosted() {  # first three argv entries are HOST run --
  /usr/bin/python3 -c 'import json,sys; a=json.loads(sys.argv[1]); sys.exit(0 if a[:3]==[sys.argv[2],"run","--"] else 1)' "$(argv_of "$1")" "$HOST"
}

loaded() { launchctl print "gui/$UID/$1" >/dev/null 2>&1; }

prefixed_plist() {  # write $1 with ProgramArguments prefixed by the host to $2
  /usr/bin/python3 - "$1" "$2" "$HOST" <<'PY'
import plistlib, sys
src, dst, host = sys.argv[1:4]
with open(src, "rb") as f:
    doc = plistlib.load(f)
argv = list(doc.get("ProgramArguments") or ([doc["Program"]] if doc.get("Program") else []))
if not argv:
    sys.exit(f"{src}: no ProgramArguments/Program")
doc.pop("Program", None)
doc["ProgramArguments"] = [host, "run", "--", *argv]
with open(dst, "wb") as f:
    plistlib.dump(doc, f)
PY
}

if [[ $APPLY == 1 ]]; then mkdir -p "$BACKUP"; chmod 0700 "$BACKUP" "$(dirname "$BACKUP")"; fi
for label in "${LABELS[@]}"; do
  plist="$AGENTS/$label.plist"
  if [[ ! -f "$plist" ]]; then echo "skip   $label (not installed)"; continue; fi
  if hosted "$plist"; then echo "ok     $label (already hosted)"; continue; fi
  stage_dir="$(mktemp -d)"; staged="$stage_dir/$label.plist"
  if [[ "$label" == com.ianva.gateway && -f "$GATEWAY_SOURCE" ]] && \
     /usr/bin/python3 -c 'import plistlib,sys; a=plistlib.load(open(sys.argv[1],"rb"))["ProgramArguments"]; sys.exit(0 if a[:3]==[sys.argv[2],"run","--"] else 1)' "$GATEWAY_SOURCE" "$HOST"; then
    cp "$GATEWAY_SOURCE" "$staged"   # reviewed, already-hosted source (after limen#3203 is live)
  else
    prefixed_plist "$plist" "$staged"
  fi
  /usr/bin/plutil -lint -s "$staged"
  was_loaded=0; loaded "$label" && was_loaded=1
  echo "change $label (loaded=$was_loaded)"
  echo "   before: $(argv_of "$plist" | cut -c1-160)"
  echo "   after:  $(argv_of "$staged" | cut -c1-160)"
  if [[ $APPLY == 1 ]]; then
    cp -p "$plist" "$BACKUP/$label.plist"
    [[ $was_loaded == 1 ]] && launchctl bootout "gui/$UID/$label" || true
    install -m 0644 "$staged" "$plist"
    if [[ $was_loaded == 1 ]]; then
      launchctl bootstrap "gui/$UID" "$plist"
      echo "   reloaded"
    fi
  fi
  rm -rf "$stage_dir"
done
[[ $APPLY == 1 ]] && echo "backups: $BACKUP" || echo "dry run only; re-run with --apply"
