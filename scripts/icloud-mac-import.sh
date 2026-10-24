#!/bin/bash
# icloud-mac-import.sh - unify: move user documents from local ~/Documents and ~/Desktop into the
# canonical iCloud taxonomy intake (same APFS volume => atomic rename). App-state dirs, dotfiles and
# the Domus TCC sentinel stay local. Writes a before/after manifest; refuses on any name collision.
#
# Usage: icloud-mac-import.sh [--dry-run] [--date YYYY-MM-DD] [--dest-root DIR]
#                             [--manifest-dir DIR] [--keep NAME]...
#   --date          import label (default 2026-10-24) -> <dest-root>/Mac-import-<date>
#   --dest-root     default ~/Library/Mobile Documents/com~apple~CloudDocs/Documents/00_Inbox_Triage
#   --manifest-dir  default /Volumes/Archive4T/icloud-dedupe-2026-10-23/manifests
#   --keep NAME     extra ~/Documents entry to leave local (adds to the built-in keep list)
# Exit: 2 usage, 3 precondition refused, 5 name collision, 7 file-count mismatch.
set -euo pipefail

DATE="2026-10-24"
DEST_ROOT="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documents/00_Inbox_Triage"
MAN_DIR="/Volumes/Archive4T/icloud-dedupe-2026-10-23/manifests"
KEEP_DOCS=(antigravity Cline Codex MuseScore4 Zoom "Max 8" "Max 9" Notes Archive Personal Work)
DRY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY="--dry-run" ;;
    --date) DATE="${2:?--date needs a value}"; shift ;;
    --dest-root) DEST_ROOT="${2:?--dest-root needs a value}"; shift ;;
    --manifest-dir) MAN_DIR="${2:?--manifest-dir needs a value}"; shift ;;
    --keep) KEEP_DOCS+=("${2:?--keep needs a value}"); shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

DEST="$DEST_ROOT/Mac-import-$DATE"
MAN="$MAN_DIR/mac-import-$DATE.tsv"

[ "$(defaults read com.apple.finder FXICloudDriveDocuments 2>/dev/null)" = "0" ] || { echo "REFUSE: D&D flag not 0"; exit 3; }

# same-volume check against the nearest existing ancestor of the destination (rename must be atomic)
probe="$DEST"
while [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
[ "$(stat -f %d "$HOME/Documents")" = "$(stat -f %d "$probe")" ] || { echo "REFUSE: not same volume"; exit 3; }

is_kept() { local n="$1" k; for k in "${KEEP_DOCS[@]}"; do [ "$n" = "$k" ] && return 0; done; return 1; }
plan=()
for src in "$HOME/Documents" "$HOME/Desktop"; do
  side=$(basename "$src")
  for p in "$src"/*; do
    [ -e "$p" ] || [ -L "$p" ] || continue   # empty dir: glob stayed literal
    n=$(basename "$p")
    [ "$side" = Documents ] && is_kept "$n" && continue
    plan+=("$side|$p")
  done
done
[ "${#plan[@]}" -gt 0 ] || { echo "nothing to import"; exit 0; }
printf '%s\n' "${plan[@]}" | sed 's/^/PLAN /'
[ "$DRY" = "--dry-run" ] && exit 0

mkdir -p "$DEST/Documents" "$DEST/Desktop" "$MAN_DIR"
: > "$MAN.tmp"
total=${#plan[@]}; i=0
for row in "${plan[@]}"; do
  side=${row%%|*}; p=${row#*|}; n=$(basename "$p"); t="$DEST/$side/$n"
  i=$((i + 1))
  [ -e "$t" ] && { echo "REFUSE collision: $t"; exit 5; }
  before=$(find "$p" \( -type f -o -type l \) | wc -l | tr -d ' ')
  mv -n "$p" "$t"
  after=$(find "$t" \( -type f -o -type l \) | wc -l | tr -d ' ')
  [ "$before" = "$after" ] || { echo "COUNT MISMATCH $p $before->$after"; exit 7; }
  printf '%s\t%s\t%s\n' "$p" "$t" "$after" >> "$MAN.tmp"
  echo "moved [$i/$total] ($after files): $p"
done
mv "$MAN.tmp" "$MAN"; echo "manifest: $MAN"
