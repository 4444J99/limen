#!/bin/bash
# Additively copy chosen NON-GIT directories to an external volume, hash-verified. Thin front-end for nongit_homing.py.
#
# WHY: a directory with no git remote has no other copy. Erase the Mac and it is gone unless it was copied somewhere
# first, and "copied" only counts once the bytes read back from the destination match the bytes read from the source.
#
#   nongit-homing.sh dry   ITEMS_TSV DEST_ROOT      read-only plan: sources are read, nothing is written to DEST_ROOT
#   HOME_NONGIT_CONFIRM=conductor-has-decided nongit-homing.sh apply ITEMS_TSV DEST_ROOT
#
# ITEMS_TSV   tab-separated, one item per line: name, source_dir, dest_rel, exclude_globs (format, the '=name'
#             carve-out and an example: scripts/mac-exit/examples/nongit-items.example.tsv)
# DEST_ROOT   an EXISTING directory on the external volume (never created here, so an unmounted volume is an error
#             and not a silent copy onto the internal disk). Each apply creates DEST_ROOT/<run name>/ and writes
#             <dest_rel>/... plus MANIFEST.sha256, MANIFEST.tsv, EXCLUDED.tsv, RESULT.txt, DRY-PLAN.log and RUN.log.
#
# What it does, per item (details and the full safety list: the docstring of nongit_homing.py)
#   * streams every regular file once, taking the SHA-256 from the bytes read, then re-reads the destination with
#     F_NOCACHE and compares; a source that changed while being copied is DRIFT, never "verified"
#   * snapshots SQLite databases (detected by their header) with `sqlite3 -readonly SRC .backup DEST`, checks them with
#     PRAGMA integrity_check and hashes them twice
#   * NEVER copies credential-looking files and directories, dataless iCloud placeholders, sockets or FIFOs: it lists
#     them by name and size in EXCLUDED.tsv
#   * nothing is deleted or overwritten; every run is a new directory; sources are never modified
# Re-verify any time:  cd <run dir> && shasum -a 256 -c MANIFEST.sha256
#
# Environment (all optional)
#   HOMING_DEADLINE_SEC          hard wall for the whole run, default 21600 (python enforces it; a perl alarm is the backstop)
#   HOMING_RUN_NAME              run directory name under DEST_ROOT, default run-<UTC stamp>-<pid>; apply refuses an existing one
#   HOMING_SCRATCH_BASE          where the scratch dir and the durable dry-plan log go, default $TMPDIR (or /var/tmp)
#   HOMING_FREE_RATIO_PCT        free space required as a percentage of the planned bytes, default 115
#   HOMING_QUIET_PROCESSES       space-separated exact process names that must NOT be running at apply (e.g. an app that
#                                owns a library package being copied); default none
#   HOMING_EXTRA_CRED_FILE_GLOBS ';'-separated credential file globs added to the built-in list (never removes one)
#   HOMING_EXTRA_CRED_DIR_GLOBS  ';'-separated credential directory globs added to the built-in list
#   NONGIT_HOMING_SQLITE         sqlite3 binary to use (default /usr/bin/sqlite3, then PATH)
#
# Exit codes: 0 ok; 1 the helper reported a problem or FAIL; 2 apply refused (no confirmation); 28 not enough (or unknown)
# free space; 64 usage / bad items file; 66 DEST_ROOT missing; 69 no sqlite3; 70 no scratch dir; 73 DEST_ROOT not
# writable or the run directory already exists; 75 a quiet-process is running; 142 backstop alarm fired.
set -u -o pipefail

MODE=${1:-}
case "$MODE" in dry | apply) ;; *)
  echo "usage: $0 dry|apply ITEMS_TSV DEST_ROOT" >&2
  exit 64
  ;;
esac
if [ "$MODE" = apply ] && [ "${HOME_NONGIT_CONFIRM:-}" != "conductor-has-decided" ]; then
  echo "REFUSED: apply is the conductor's decision. Re-run with HOME_NONGIT_CONFIRM=conductor-has-decided after a clean dry run." >&2
  exit 2
fi
ITEMS=${2:-}
DEST_ROOT=${3:-}
if [ -z "$ITEMS" ] || [ -z "$DEST_ROOT" ]; then
  echo "usage: $0 dry|apply ITEMS_TSV DEST_ROOT" >&2
  exit 64
fi
[ -f "$ITEMS" ] || { echo "no such items file: $ITEMS" >&2; exit 64; }
case "$DEST_ROOT" in /*) ;; *) echo "DEST_ROOT must be an absolute path: $DEST_ROOT" >&2; exit 64 ;; esac
DEST_ROOT=${DEST_ROOT%/}
[ -d "$DEST_ROOT" ] || { echo "DEST_ROOT is not an existing directory (is the volume mounted?): $DEST_ROOT" >&2; exit 66; }

HERE=$(cd -P "$(dirname "$0")" && pwd -P)
HELPER="$HERE/nongit_homing.py"
[ -f "$HELPER" ] || { echo "missing helper: $HELPER" >&2; exit 70; }
DEADLINE=${HOMING_DEADLINE_SEC:-21600}
RATIO=${HOMING_FREE_RATIO_PCT:-115}
case "$DEADLINE$RATIO" in '' | *[!0-9]*) echo "HOMING_DEADLINE_SEC and HOMING_FREE_RATIO_PCT must be whole numbers" >&2; exit 64 ;; esac
SCRATCH_BASE=${HOMING_SCRATCH_BASE:-${TMPDIR:-/var/tmp}}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_NAME=${HOMING_RUN_NAME:-run-$STAMP-$$}
case "$RUN_NAME" in '' | . | .. | *[!A-Za-z0-9._-]*) echo "HOMING_RUN_NAME must be a plain name (letters, digits, . _ -): $RUN_NAME" >&2; exit 64 ;; esac
RUN="$DEST_ROOT/$RUN_NAME"

SQLITE_BIN=${NONGIT_HOMING_SQLITE:-}
if [ -z "$SQLITE_BIN" ]; then
  if [ -x /usr/bin/sqlite3 ]; then SQLITE_BIN=/usr/bin/sqlite3; else SQLITE_BIN=$(command -v sqlite3 || true); fi
fi
{ [ -n "$SQLITE_BIN" ] && [ -x "$SQLITE_BIN" ]; } || { echo "missing sqlite3 (set NONGIT_HOMING_SQLITE)" >&2; exit 69; }

umask 077
SCRATCH=$(mktemp -d "$SCRATCH_BASE/nongit-homing.XXXXXX") || { echo "cannot create scratch dir under $SCRATCH_BASE" >&2; exit 70; }
trap 'rm -rf "$SCRATCH"' EXIT

run_helper() { # mode run_dir
  local prefix=()
  command -v taskpolicy >/dev/null 2>&1 && prefix=(taskpolicy -b)
  # python enforces DEADLINE itself (and writes a FAIL result); the perl alarm is only a backstop for a hung read.
  perl -e 'alarm shift; exec @ARGV' $((DEADLINE + 60)) ${prefix[@]+"${prefix[@]}"} python3 -I "$HELPER" "$1" "$2" "$ITEMS" \
    --home "$HOME" --sqlite "$SQLITE_BIN" --deadline-sec "$DEADLINE" \
    --extra-cred-file-globs "${HOMING_EXTRA_CRED_FILE_GLOBS:-}" --extra-cred-dir-globs "${HOMING_EXTRA_CRED_DIR_GLOBS:-}"
}

echo "== nongit-homing.sh $MODE  $(date -u +%FT%TZ)  dest=$DEST_ROOT  run=$RUN_NAME"
echo "== pass 1: dry plan (reads sources, writes nothing outside $SCRATCH)"
run_helper dry "$RUN" > "$SCRATCH/dry.log" 2>&1
rc=$?
cp "$SCRATCH/dry.log" "$SCRATCH_BASE/nongit-homing-dry-$STAMP.log" # durable copy of the full plan, outside the scratch dir
grep -Ev '^(excluded\[|sqlite_store=)' "$SCRATCH/dry.log"
echo "sqlite stores: $(grep -c '^sqlite_store=' "$SCRATCH/dry.log") (open-failed: $(grep -c 'OPEN-FAILED' "$SCRATCH/dry.log")); excluded rows listed: $(grep -c '^excluded\[' "$SCRATCH/dry.log"); full plan: $SCRATCH_BASE/nongit-homing-dry-$STAMP.log"
if [ "$rc" -ne 0 ]; then
  [ "$rc" -eq 142 ] && echo "dry pass killed by the backstop alarm (deadline $DEADLINE s + 60 s)" >&2
  echo "dry pass failed rc=$rc" >&2
  exit "$rc"
fi

# Free space: refuse when either number is unknown (fail closed), measured on the destination directory itself.
PLAN=$(sed -n 's/^PLAN_TOTAL_BYTES=//p' "$SCRATCH/dry.log")
FREE_KB=$(df -Pk "$DEST_ROOT" | awk 'NR==2{print $4}')
case "$PLAN" in '' | *[!0-9]*) echo "cannot read the planned byte total from the dry plan; refusing" >&2; exit 28 ;; esac
case "$FREE_KB" in '' | *[!0-9]*) echo "cannot read free space on $DEST_ROOT; refusing" >&2; exit 28 ;; esac
NEED_KB=$((((PLAN + 1023) * RATIO / 100 + 1023) / 1024))
echo "planned bytes: $PLAN   free on $DEST_ROOT: $FREE_KB KiB   required: $NEED_KB KiB (${RATIO}% of plan)"
if [ "$FREE_KB" -lt "$NEED_KB" ]; then
  echo "NOT ENOUGH FREE SPACE: need ~$NEED_KB KiB, have $FREE_KB KiB" >&2
  exit 28
fi

if [ "$MODE" = dry ]; then
  echo "== dry run complete; nothing was written to $DEST_ROOT. Next (conductor only):"
  echo "   HOME_NONGIT_CONFIRM=conductor-has-decided $0 apply $ITEMS $DEST_ROOT"
  exit 0
fi

[ -w "$DEST_ROOT" ] || { echo "$DEST_ROOT is not writable" >&2; exit 73; }
[ -e "$RUN" ] && { echo "REFUSED: run directory already exists: $RUN (a run is never reused)" >&2; exit 73; }
for proc in ${HOMING_QUIET_PROCESSES:-}; do
  if pgrep -x "$proc" > /dev/null 2>&1; then echo "REFUSED: $proc is running; quit it (do not open it) and retry" >&2; exit 75; fi
done

echo "== pass 2: apply into $RUN"
run_helper apply "$RUN" 2>&1 | tee "$SCRATCH/apply.log"
rc=${PIPESTATUS[0]}
# rc 73 = the helper refused an existing run dir: it is someone else's, so leave it exactly as it was.
if [ "$rc" -ne 73 ] && [ -d "$RUN" ]; then
  if [ ! -e "$RUN/RESULT.txt" ]; then
    printf 'RESULT: FAIL (helper exited %s before writing a result; MANIFEST.sha256 lists only what was verified so far)\n' "$rc" > "$RUN/RESULT.txt"
  fi
  cp -n "$SCRATCH/dry.log" "$RUN/DRY-PLAN.log"
  cp -n "$SCRATCH/apply.log" "$RUN/RUN.log"
fi
echo "== exit $rc ; result file: $RUN/RESULT.txt"
echo "== re-verify any time:  cd '$RUN' && shasum -a 256 -c MANIFEST.sha256"
exit "$rc"
