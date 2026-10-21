#!/bin/bash
# Mount ONE Time Machine APFS snapshot read-only, so an older backup than the ones macOS exposes can be read by tm-rescue.sh.
#
# WHY: a Time Machine volume keeps one APFS snapshot per backup, but macOS only surfaces some of them under
# /Volumes/.timemachine. Mounting one explicitly lets tm-vanished.sh and tm-rescue.sh read it. Nothing is written to the
# snapshot or to the Mac; the only side effect is one read-only mount and, on unmount, removal of the EMPTY mount-point
# directory.
#
#   bash tm-mount-snapshot.sh dry   VOLUME SNAPSHOT [MOUNTPOINT]    print what would run; needs no privilege
#   sudo bash tm-mount-snapshot.sh apply VOLUME SNAPSHOT [MOUNTPOINT]   mount it read-only (macOS requires root)
#   sudo bash tm-mount-snapshot.sh unmount [MOUNTPOINT]             unmount it and remove the empty mount-point directory
#
# VOLUME    the Time Machine volume's name or device node, as `diskutil list` shows it (required: there is no default).
# SNAPSHOT  the full APFS snapshot name from `diskutil apfs listSnapshots VOLUME` (com.apple.TimeMachine.<stamp>.backup), or
#           just the <stamp> YYYY-MM-DD-HHMMSS. Matched EXACTLY, never as a substring.
# MOUNTPOINT  absolute path, default /tmp/tm-snapshot-mount. It must not exist yet, or be an empty directory.
#
# All three are ARGUMENTS on purpose: sudo resets the environment, so an env var would let `dry` show one mount point
# while `apply` used another. After a mount, read it with TM_ROOT=<mountpoint> (tm-lib.sh probes the layout
# <mountpoint>/<stamp>.backup/<TM_REL_ROOT>).
set -u
default_mp=/tmp/tm-snapshot-mount
mode="${1:-dry}"

fail() { echo "FAIL: $*" >&2; exit 2; }

case "$mode" in
  dry|apply) vol="${2:-}"; snap="${3:-}"; mp="${4:-$default_mp}"
             [[ -n "$vol" && -n "$snap" ]] || fail "usage: tm-mount-snapshot.sh $mode VOLUME SNAPSHOT [MOUNTPOINT]" ;;
  unmount)   mp="${2:-$default_mp}" ;;
  *)         fail "mode must be dry, apply or unmount" ;;
esac

[[ "$mp" == /* && "$mp" != / ]] || fail "MOUNTPOINT must be an absolute path other than /: $mp"
[[ ! -L "$mp" ]] || fail "MOUNTPOINT is a symbolic link; refusing: $mp"
mp_parent="$(cd -P "$(dirname "$mp")" 2>/dev/null && pwd -P)" || fail "parent of MOUNTPOINT does not exist: $(dirname "$mp")"
mp_real="${mp_parent%/}/$(basename "$mp")"   # mount(8) reports resolved paths (/tmp is /private/tmp)

is_mounted() { mount | awk -v p="$mp_real" 'index($0, " on " p " (") > 0 { f = 1 } END { exit !f }'; }

if [[ "$mode" == unmount ]]; then
  [[ "$(id -u)" == 0 ]] || fail "unmount needs root: sudo bash '$0' unmount '$mp'"
  is_mounted || { echo "not mounted at $mp_real"; exit 0; }
  umount "$mp_real" || fail "umount failed"
  rmdir "$mp_real" 2>/dev/null
  echo "UNMOUNTED and removed $mp_real"
  exit 0
fi

case "$snap" in
  com.apple.TimeMachine.*) ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]) snap="com.apple.TimeMachine.$snap.backup" ;;
  *) fail "SNAPSHOT must be a full APFS snapshot name or a YYYY-MM-DD-HHMMSS stamp: $snap" ;;
esac

dev="$(diskutil info "$vol" 2>/dev/null | awk -F': *' '/Device Node/ {print $2; exit}')"
[[ -n "$dev" ]] || fail "volume '$vol' not found; connect the Time Machine drive and check \`diskutil list\`"
snaps="$(diskutil apfs listSnapshots "$vol" 2>/dev/null)" || fail "cannot list the snapshots of '$vol'"
printf '%s\n' "$snaps" | awk -v want="$snap" '{ for (i = 1; i < NF; i++) if ($i == "Name:" && $(i + 1) == want) f = 1 } END { exit !f }' ||
  fail "snapshot '$snap' is not on $vol ($dev); see \`diskutil apfs listSnapshots '$vol'\`"

mounted=no; is_mounted && mounted=yes

if [[ "$mode" == dry ]]; then
  echo "volume    : $vol  ($dev)"
  echo "snapshot  : $snap  (present)"
  echo "mountpoint: $mp_real  (currently mounted: $mounted)"
  echo "would run : mkdir -m 700 '$mp_real'   (only if it does not exist)"
  echo "            mount_apfs -o rdonly,nobrowse -s '$snap' '$dev' '$mp_real'"
  echo "apply with: sudo bash '$0' apply '$vol' '$snap' '$mp'"
  exit 0
fi

[[ "$(id -u)" == 0 ]] || fail "apply needs root: sudo bash '$0' apply '$vol' '$snap' '$mp'"
if [[ "$mounted" == yes ]]; then echo "already mounted at $mp_real"; exit 0; fi
created=no
if [[ -e "$mp_real" ]]; then
  [[ -d "$mp_real" ]] || fail "MOUNTPOINT exists and is not a directory: $mp_real"
  [[ -z "$(find "$mp_real" -mindepth 1 -maxdepth 1 -print 2>/dev/null | head -n 1)" ]] ||
    fail "MOUNTPOINT exists and is not empty; refusing to mount over it: $mp_real"
else
  mkdir -m 700 "$mp_real" || fail "cannot create $mp_real"
  created=yes
fi
if mount_apfs -o rdonly,nobrowse -s "$snap" "$dev" "$mp_real"; then
  echo "MOUNTED read-only: $snap at $mp_real"
  echo "read it with: TM_ROOT='$mp_real'"
  find "$mp_real" -mindepth 1 -maxdepth 1 -print | head -n 5
else
  [[ "$created" == yes ]] && rmdir "$mp_real" 2>/dev/null
  fail "mount_apfs failed"
fi
