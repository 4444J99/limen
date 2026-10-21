#!/bin/bash
# Prove a tm-rescue.sh destination equals the Time Machine backup it was copied from, file by file.
#
# WHY: a rescue is only worth trusting once the copy is shown identical to its source, and Time Machine thins hourly backups
# after about 24 hours -- once this passes, the copy no longer depends on the backup surviving. The comparison re-reads the
# BACKUP (sha256 of every file, plus directories and symlink targets), never the copy's own manifest: a manifest generated
# from a damaged copy would "verify" the damage.
#
#   tm-rescue-verify.sh dry   DEST     compare and report; writes nothing in DEST (the default mode)
#   tm-rescue-verify.sh apply DEST     the same, and on PASS/PARTIAL write RESCUE-MANIFEST.sha256 and RESCUE-VERIFY.txt there
#
# DEST (argument, or $TM_DEST) is a directory made by tm-rescue.sh. Environment: TM_ROOT locates the backups again
# (tm-lib.sh). The exclude list and backup-relative root are read from DEST/RESCUE-RECEIPT.txt, so they cannot drift from
# what the copier used; TM_REL_ROOT in the environment overrides the receipt. A receipt may only name default-list excludes
# unless TM_EXCLUDES is set to exactly its list (a doctored receipt must not be able to hide damage); if TM_EXCLUDES is set
# at all it must equal the receipt's list.
#
# Only rows whose status is "copied" are compared. Per row:
#   identical   same files (sha256), directories and symlink targets as the backup
#   MISMATCH    anything differs, a side is unreadable or missing, or the row has no files (a vacuous match is not a match)
# RESULT: PASS    every row identical;  PARTIAL  all copied rows identical but some rows were never copied (still exit 1);
#         FAIL    any MISMATCH. Exit 0 only on PASS; 2 on refusal or bad input. DEST/RESCUE-MANIFEST.sha256 is checkable with
#         `cd DEST && shasum -a 256 -c RESCUE-MANIFEST.sha256`. On FAIL the comparison files are kept in a temp directory.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tm-lib.sh
. "$here/tm-lib.sh"

mode=dry
case "${1:-}" in dry|apply) mode="$1"; shift ;; esac
dest="${1:-${TM_DEST:-}}"
[[ -n "$dest" && -d "$dest" ]] || tm_die "need a rescue destination directory: tm-rescue-verify.sh [dry|apply] DEST"
dest="$(cd -P "$dest" && pwd -P)"
results="$dest/RESCUE-RESULTS.tsv"; receipt="$dest/RESCUE-RECEIPT.txt"
[[ -f "$results" && -f "$receipt" ]] || tm_die "$dest has no RESCUE-RESULTS.tsv / RESCUE-RECEIPT.txt; not a tm-rescue.sh destination"
grep -q '^excludes:' "$receipt" || tm_die "$receipt records no exclude list; cannot compare like with like"
if [[ "$mode" == apply ]]; then
  for f in RESCUE-MANIFEST.sha256 RESCUE-VERIFY.txt; do
    [[ -e "$dest/$f" ]] && tm_die "$dest/$f already exists; refusing to overwrite"
  done
fi

# The receipt says what the copier left out. It is also the one input a damaged or doctored copy could use to hide damage
# (widen the list until the damaged file is "excluded"), so it is only trusted for names in the default list; any other
# name must be confirmed by setting TM_EXCLUDES to exactly the receipt's list.
norm() { printf '%s' "$1" | tr -s ' \t' '  ' | sed 's/^ //; s/ $//'; }
rec_excl="$(norm "$(sed -n 's/^excludes:[[:space:]]*//p' "$receipt")")"
if [[ -n "${TM_EXCLUDES+x}" ]]; then
  [[ "$(norm "$TM_EXCLUDES")" == "$rec_excl" ]] || tm_die "TM_EXCLUDES ($(norm "$TM_EXCLUDES")) differs from the receipt's exclude list ($rec_excl)"
else
  read -r -a rec_names <<< "$rec_excl"
  for n in ${rec_names[@]+"${rec_names[@]}"}; do
    case " $TM_DEFAULT_EXCLUDES " in
      *" $n "*) ;;
      *) tm_die "the receipt excludes '$n', which is not in the default exclude list; if that is intended, set TM_EXCLUDES to the receipt's list ($rec_excl)" ;;
    esac
  done
fi
TM_EXCLUDES="$rec_excl"
if [[ -z "${TM_REL_ROOT:-}" ]]; then TM_REL_ROOT="$(sed -n 's/^rel_root:[[:space:]]*//p' "$receipt")"; fi
tm_init

umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/tm-rescue-verify.XXXXXX")" || tm_die "cannot create a temp directory"
: > "$work/manifest.all"
echo "mode: $mode$([[ "$mode" == dry ]] && echo ' (nothing will be written in the destination)')"
echo "excludes (from the receipt): ${TM_EXCLUDES_EFFECTIVE:-none}"

idx=0; ok_rows=0; bad_rows=0; uncopied=0; files=0; lineno=0
while IFS=$'\t' read -r rel stamp status _rest <&3; do
  lineno=$((lineno + 1))
  [[ "$lineno" == 1 ]] && continue   # header
  if [[ "$status" != copied ]]; then
    printf 'NOT-COPIED  %-34s %s/%s\n' "$status" "$stamp" "$rel"; uncopied=$((uncopied + 1)); continue
  fi
  idx=$((idx + 1))
  row_bad=""
  src=""; dst="$dest/$stamp/$rel"
  if ! home="$(tm_snap_home "$stamp")"; then row_bad="backup $stamp is unreadable"
  else
    src="$home/$rel"
    if [[ -L "$src" || ! -d "$src" ]]; then row_bad="directory is missing in the backup"
    elif [[ -L "$dst" || ! -d "$dst" ]]; then row_bad="the copy is missing"
    else
      # the reference must be the backup itself, never something inside the destination
      src_real="$(cd -P "$src" && pwd -P)"
      case "$src_real/" in "$dest"/*) row_bad="source resolves inside the destination" ;; esac
    fi
  fi
  n=0
  if [[ -z "$row_bad" ]]; then
    err="$work/$idx.err"; : > "$err"; rc=0
    tm_inventory "$src" "$err" > "$work/$idx.inv.src" || rc=1
    tm_inventory "$dst" "$err" > "$work/$idx.inv.dst" || rc=1
    tm_hash_manifest "$src" "$err" > "$work/$idx.sha.src" || rc=1
    tm_hash_manifest "$dst" "$err" > "$work/$idx.sha.dst" || rc=1
    if [[ "$rc" != 0 || -s "$err" ]]; then row_bad="a file or directory could not be read (details: $err)"
    else
      n="$(wc -l < "$work/$idx.sha.src" | tr -d ' ')"
      if [[ "$n" == 0 ]]; then row_bad="no files to compare"
      else
        if ! cmp -s "$work/$idx.inv.src" "$work/$idx.inv.dst"; then
          row_bad="files, directories or symlinks differ"; diff "$work/$idx.inv.src" "$work/$idx.inv.dst" > "$work/$idx.inv.diff"
        fi
        if ! cmp -s "$work/$idx.sha.src" "$work/$idx.sha.dst"; then
          row_bad="${row_bad:+$row_bad; }file contents differ"; diff "$work/$idx.sha.src" "$work/$idx.sha.dst" > "$work/$idx.sha.diff"
        fi
      fi
    fi
  fi
  if [[ -n "$row_bad" ]]; then
    printf 'MISMATCH    %s/%s  (%s)\n' "$stamp" "$rel" "$row_bad"
    for d in "$work/$idx.inv.diff" "$work/$idx.sha.diff"; do
      [[ -s "$d" ]] && head -n 8 "$d" | sed 's/^/              /'
    done
    bad_rows=$((bad_rows + 1)); continue
  fi
  printf 'identical   %6s files  %s/%s\n' "$n" "$stamp" "$rel"
  ok_rows=$((ok_rows + 1)); files=$((files + n))
  # manifest lines come from the BACKUP side (just proven equal to the copy), with paths relative to DEST
  awk -v p="$stamp/$rel" '{ i = index($0, "  "); h = substr($0, 1, i - 1); r = substr($0, i + 2); sub(/^\.\//, "", r); print h "  " p "/" r }' \
    "$work/$idx.sha.src" >> "$work/manifest.all"
done 3< "$results"

result=PASS
if [[ "$bad_rows" != 0 ]]; then result=FAIL
elif [[ "$ok_rows" == 0 ]]; then result=FAIL; echo "nothing was verified: no row of $results has status copied"
elif [[ "$uncopied" != 0 ]]; then result=PARTIAL; fi

if [[ "$mode" == apply && "$result" != FAIL ]]; then
  mv "$work/manifest.all" "$dest/RESCUE-MANIFEST.sha256"
  {
    echo "rescue verification: $result"
    echo "verified_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "rows_verified: $ok_rows"
    echo "rows_not_copied: $uncopied"
    echo "files_sha256_identical: $files"
    echo "compared_against: the Time Machine backup itself, re-hashed at verification time (not the copy's own manifest)"
    echo "rel_root: $TM_REL_ROOT"
    echo "excludes: $TM_EXCLUDES_EFFECTIVE"
  } > "$dest/RESCUE-VERIFY.txt"
  echo "wrote $dest/RESCUE-MANIFEST.sha256 and $dest/RESCUE-VERIFY.txt"
fi

if [[ "$result" == FAIL ]]; then
  echo "comparison files kept in $work"
  echo "RESULT: FAIL ($bad_rows mismatched row(s), $ok_rows identical)"; exit 1
fi
rm -rf "$work"
if [[ "$result" == PARTIAL ]]; then echo "RESULT: PARTIAL ($ok_rows identical, $uncopied row(s) were never copied)"; exit 1; fi
echo "RESULT: PASS ($files files across $ok_rows row(s))"; exit 0
