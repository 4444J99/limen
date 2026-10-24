#!/usr/bin/env bash
# iphone-offload.sh - encrypted full backup + DCIM pull from a connected, trusted iPhone.
# Never deletes anything from the phone. Never handles a backup password.
#
# Usage: iphone-offload.sh [--dry-run] [--udid UDID] [--dest-root DIR] [--afc-timeout SECONDS]
#   --udid          pin a device (default: the single USB-connected device, detected via
#                   pymobiledevice3; $PYMOBILEDEVICE3_UDID also honoured). Several USB devices => abort.
#   --dest-root     default /Volumes/Archive4T/iphone-offload  (writes <dest-root>/<UDID>/<YYYYMMDD>/)
#   --afc-timeout   hard wall for the DCIM pull in seconds (default 14400)
# Long phases (backup, DCIM pull) print a heartbeat line every 60s with bytes written so far.
set -euo pipefail

DEST_ROOT="/Volumes/Archive4T/iphone-offload"
AFC_TIMEOUT=14400   # 4h hard wall for the DCIM pull
DRY_RUN=0
UDID="${PYMOBILEDEVICE3_UDID:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --udid) UDID="${2:?--udid needs a value}"; shift ;;
    --dest-root) DEST_ROOT="${2:?--dest-root needs a value}"; shift ;;
    --afc-timeout) AFC_TIMEOUT="${2:?--afc-timeout needs a value}"; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "ABORT: $*" >&2; exit 1; }
command -v pymobiledevice3 >/dev/null || die "pymobiledevice3 not on PATH (pipx install pymobiledevice3)"
command -v jq >/dev/null || die "jq not on PATH"

# Hard-timeout wrapper: gtimeout, then timeout, then perl alarm.
run_timeout() {
  local secs="$1"; shift
  if command -v gtimeout >/dev/null; then gtimeout --signal=TERM "$secs" "$@"
  elif command -v timeout >/dev/null; then timeout --signal=TERM "$secs" "$@"
  else perl -e 'alarm shift; exec @ARGV or die "exec: $!"' "$secs" "$@"
  fi
}

# Heartbeat: a line every 60s (dir size) while a long command runs; never let a phase go silent.
HB_PID=""
start_heartbeat() {
  local label="$1" dir="$2" t0; t0="$(date +%s)"
  ( while sleep 60; do
      echo "heartbeat [$label] elapsed $(( $(date +%s) - t0 ))s, written $(du -sk "$dir" 2>/dev/null | awk '{print $1*1024}') bytes in $dir"
    done ) &
  HB_PID=$!
}
stop_heartbeat() { [ -n "$HB_PID" ] && kill "$HB_PID" 2>/dev/null || true; HB_PID=""; }
trap stop_heartbeat EXIT

# --- a. list device, print model / iOS / storage -------------------------------
echo "== usbmux devices =="
pymobiledevice3 usbmux list
if [ -z "$UDID" ]; then
  USB_LIST="$(pymobiledevice3 usbmux list --usb)"
  [ "$(jq 'length' <<<"$USB_LIST")" -le 1 ] || die "several USB devices attached; pin one with --udid"
  UDID="$(jq -r '.[0].UniqueDeviceID // empty' <<<"$USB_LIST")"
fi
[ -n "$UDID" ] || die "no USB-connected iPhone found (plug in, unlock, tap Trust)"
DEV=(--udid "$UDID")

INFO="$(pymobiledevice3 lockdown info "${DEV[@]}")" || die "lockdown info failed (unlock the phone and tap Trust)"
DISK="$(pymobiledevice3 lockdown get com.apple.disk_usage "${DEV[@]}")" || DISK='{}'

MODEL="$(jq -r '.ProductType // "unknown"' <<<"$INFO")"
IOS="$(jq -r '.ProductVersion // "unknown"' <<<"$INFO")"
NAME="$(jq -r '.DeviceName // "unknown"' <<<"$INFO")"
TOTAL="$(jq -r '.TotalDiskCapacity // .TotalDataCapacity // 0' <<<"$DISK")"
AVAIL="$(jq -r '.AmountDataAvailable // .TotalDataAvailable // 0' <<<"$DISK")"
USED=$(( TOTAL - AVAIL ))
[ "$TOTAL" -gt 0 ] || die "could not read storage capacity from com.apple.disk_usage"

echo "== device =="
echo "name:     $NAME"
echo "udid:     $UDID"
echo "model:    $MODEL"
echo "iOS:      $IOS"
echo "capacity: $TOTAL bytes"
echo "free:     $AVAIL bytes"
echo "used:     $USED bytes"

TODAY="$(date +%Y%m%d)"
BASE="$DEST_ROOT/$UDID/$TODAY"
NEED=$(( USED * 13 / 10 ))

WILL_ENCRYPT="$(pymobiledevice3 lockdown get com.apple.mobile.backup WillEncrypt "${DEV[@]}" 2>/dev/null | tr -d '[:space:]' | tr 'A-Z' 'a-z' || true)"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "== DRY RUN plan (nothing written, nothing sent to phone beyond read-only queries) =="
  echo "dest:            $BASE (dirs mode 0700: backup/ DCIM/)"
  echo "space required:  >= $NEED bytes (1.3 x used) free on $(dirname "$DEST_ROOT")"
  echo "encryption:      WillEncrypt=${WILL_ENCRYPT:-unknown}"
  echo "1. check free space on volume"
  echo "2. require encrypted backups ON, else print the command for you to run and stop"
  echo "3. pymobiledevice3 backup2 backup --full $BASE/backup  (prompts for password if needed)"
  echo "4. pymobiledevice3 afc pull /DCIM $BASE/DCIM  (hard timeout ${AFC_TIMEOUT}s)"
  echo "5. write $BASE/DCIM.sha256 and $BASE/receipt.json"
  echo "6. nothing is deleted from the phone"
  exit 0
fi

# --- b/c. volume + free-space gate ----------------------------------------------
VOL="$(dirname "$DEST_ROOT")"
[ -d "$VOL" ] || die "volume not mounted: $VOL"
FREE_KB="$(df -k "$VOL" | awk 'NR==2{print $4}')"
FREE=$(( FREE_KB * 1024 ))
echo "dest free: $FREE bytes; required: $NEED bytes"
[ "$FREE" -ge "$NEED" ] || die "insufficient space on $VOL (need $NEED, have $FREE)"

umask 077
mkdir -p "$DEST_ROOT" "$DEST_ROOT/$UDID" "$BASE" "$BASE/backup" "$BASE/DCIM"
chmod 0700 "$DEST_ROOT/$UDID" "$BASE" "$BASE/backup" "$BASE/DCIM"

# --- d. encrypted backup gate ----------------------------------------------------
if [ "$WILL_ENCRYPT" != "true" ]; then
  echo "Backup encryption is NOT enabled on the phone (WillEncrypt=${WILL_ENCRYPT:-unknown})." >&2
  echo "Run this yourself (choose a password and store it in your password manager), then re-run:" >&2
  echo "  pymobiledevice3 backup2 encryption on --udid $UDID -b $BASE/backup" >&2
  echo "(omit the password argument if the tool prompts; do not paste it into shared logs)" >&2
  exit 3
fi

START_EPOCH="$(date +%s)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "== encrypted full backup =="
start_heartbeat backup "$BASE/backup"
pymobiledevice3 backup2 backup --full "$BASE/backup" "${DEV[@]}"
stop_heartbeat

# --- e. DCIM pull -----------------------------------------------------------------
echo "== DCIM pull (timeout ${AFC_TIMEOUT}s) =="
start_heartbeat dcim "$BASE/DCIM"
run_timeout "$AFC_TIMEOUT" pymobiledevice3 afc pull --ignore-errors /DCIM "$BASE/DCIM" "${DEV[@]}" \
  || echo "WARNING: DCIM pull ended non-zero or timed out; manifest reflects what was pulled" >&2
stop_heartbeat

# --- f. manifest + receipt ----------------------------------------------------------
echo "== manifest =="
MANIFEST="$BASE/DCIM.sha256"
( cd "$BASE/DCIM" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 ) > "$MANIFEST"
FILES="$(wc -l < "$MANIFEST" | tr -d ' ')"
BYTES="$(find "$BASE/DCIM" -type f -exec stat -f %z {} + | awk '{s+=$1} END{print s+0}')"
BACKUP_BYTES="$(du -sk "$BASE/backup" | awk '{print $1*1024}')"
END_EPOCH="$(date +%s)"
END_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

jq -n \
  --arg udid "$UDID" --arg model "$MODEL" --arg ios "$IOS" --arg start "$START_ISO" --arg end "$END_ISO" \
  --arg base "$BASE" --arg manifest "$MANIFEST" \
  --argjson dcim_files "$FILES" --argjson dcim_bytes "$BYTES" --argjson backup_bytes "$BACKUP_BYTES" \
  --argjson duration "$(( END_EPOCH - START_EPOCH ))" \
  --argjson phone_used "$USED" --argjson phone_total "$TOTAL" \
  '{udid:$udid,model:$model,ios:$ios,start:$start,end:$end,duration_seconds:$duration,
    dest:$base,backup_encrypted:true,backup_bytes:$backup_bytes,
    dcim:{files:$dcim_files,bytes:$dcim_bytes,manifest:$manifest},
    phone:{used_bytes:$phone_used,capacity_bytes:$phone_total},
    deleted_from_phone:0}' > "$BASE/receipt.json"
chmod 0600 "$BASE/receipt.json" "$MANIFEST"

echo "== done =="
cat "$BASE/receipt.json"
