#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin" "$TMP/workspace"
cat >"$TMP/bin/df" <<'SH'
#!/usr/bin/env bash
cat <<'OUT'
Filesystem 1024-blocks     Used Available Capacity Mounted on
/dev/fake     100000000 93000000  33554432      93% /tmp/fake
OUT
SH
chmod +x "$TMP/bin/df"

OUT="$(
  PATH="$TMP/bin:$PATH" \
  LIMEN_ROOT="$ROOT" \
  LIMEN_WORKDIR="$TMP/workspace" \
  LIMEN_RECLAIM_DRYRUN=1 \
  LIMEN_CLONE_REAP_APPLY=0 \
  LIMEN_BRANCH_REAP_APPLY=0 \
  LIMEN_NM_IDLE_DAYS=7 \
  bash "$ROOT/scripts/clone-maintenance.sh"
)"

grep -F "93% used, 32GiB free" <<<"$OUT" >/dev/null
grep -F "pressure=off" <<<"$OUT" >/dev/null
grep -F "idle=7d" <<<"$OUT" >/dev/null
if grep -F "pressure: capture" <<<"$OUT" >/dev/null; then
  echo "clone-maintenance entered pressure capture despite adequate free space" >&2
  exit 1
fi
