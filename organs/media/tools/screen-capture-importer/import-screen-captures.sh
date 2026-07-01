#!/usr/bin/env bash
# import-screen-captures.sh — import NEW screengrabs & recordings into Photos.app.
#
# Carrier-Wave Media organ · capture front-end (Spine A intake). Rescued into git
# 2026-07-01 from the live-but-untracked ~/.local/bin copy (provenance fix).
#
# Watches CAPTURE_DIR for new png/jpg/heic/mov/mp4/m4v, imports each once (idempotent
# via a seen-list), skipping Photos' own duplicate check. Driven by the LaunchAgent
# com.user.photos-screen-capture-importer (see install.sh) on a WatchPath trigger.
#
# NOTE (exit-1 cause on record): the `tell application "Photos" ... import` step fails
# with AppleScript error -4960 until this process is granted Automation permission to
# control Photos.app (System Settings -> Privacy & Security -> Automation). That grant
# is the human atom; see README.md and lever L-TCC-PHOTOS-AUTOMATION.
set -Eeuo pipefail

CAPTURE_DIR="${CAPTURE_DIR:-$HOME/Pictures/Screen Captures}"
STATE_DIR="$HOME/Library/Application Support/photos-screen-capture-importer"
STATE="$STATE_DIR/imported.txt"
mkdir -p "$STATE_DIR"
touch "$STATE"

TMP="$(mktemp)"
NEW="$(mktemp)"
trap 'rm -f "$TMP" "$NEW"' EXIT

find "$CAPTURE_DIR" -maxdepth 1 -type f \( \
  -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.heic' -o \
  -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' \
\) -print | sort > "$TMP"

python3 - "$STATE" "$TMP" "$NEW" <<'PY'
import sys
state, src, out = sys.argv[1:4]
seen = set(open(state, errors="ignore").read().splitlines())
new = [p.strip() for p in open(src, errors="ignore") if p.strip() and p.strip() not in seen]
open(out, "w").write("\n".join(new) + ("\n" if new else ""))
PY

[ -s "$NEW" ] || exit 0

osascript - "$NEW" <<'APPLESCRIPT'
on run argv
  set listFile to item 1 of argv
  set txt to read POSIX file listFile
  set importFiles to {}
  repeat with p in paragraphs of txt
    if p is not "" then set end of importFiles to POSIX file p
  end repeat
  if (count of importFiles) > 0 then
    tell application "Photos"
      import importFiles skip check duplicates yes
    end tell
  end if
end run
APPLESCRIPT

cat "$NEW" >> "$STATE"
