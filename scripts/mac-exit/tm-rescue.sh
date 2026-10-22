#!/bin/bash
# Copy directories out of a Time Machine backup into a NEW directory on an external volume, then re-inventory the copies.
#
# WHY: after a repository vanishes from the Mac, the newest Time Machine backup that still has it can be the only place its
# unique work survives, and Time Machine thins hourly backups after about 24 hours, so the window to copy it out is finite.
# The backup is only read; the destination is a NEW directory; nothing is deleted or modified anywhere, and an existing
# destination is never overwritten. Prove the copies with tm-rescue-verify.sh afterwards.
#
#   tm-rescue.sh dry   [PLAN]     read-only: size, git kind and presence of every planned directory, then the destination
#                                 checks apply would make ("WOULD REFUSE: ..."). Exit 0 all present; 1 something missing in
#                                 its backup; 2 apply would refuse (the listing is still printed first)
#   tm-rescue.sh apply [PLAN]     copy, re-inventory, write the results and receipt; exit 0 only when every row is green
#
# PLAN (argument, or $TM_PLAN) is a text file, one directory per line: "rel<TAB>snapshot", where rel is relative to $HOME
# (or an absolute path below it) and snapshot is a backup stamp YYYY-MM-DD-HHMMSS. A bare "rel" line uses $TM_STAMP.
# '#' lines and the header line are skipped. tm-vanished.sh writes such a plan; so can a human.
#
# Environment (tm-lib.sh documents TM_ROOT, TM_REL_ROOT, TM_EXCLUDES):
#   TM_STAMP               snapshot for plan lines that name none
#   TM_DEST_ROOT           EXISTING directory on the external volume; the run directory is created inside it
#                          (recovered-from-tm-<stamp>, or ...-<newest stamp>-and-earlier for a multi-snapshot plan)
#   TM_DEST                a NEW directory to use instead of that default name (its parent must exist)
#                          Apply also refuses when the copied size (excluded names not counted) exceeds the free space there.
#   TM_ALLOW_INTERNAL_DEST=1   permit a destination on the same device as $HOME. Refused otherwise: rescuing onto the disk
#                          about to be erased defeats the purpose, and an unmounted volume's leftover mount-point directory
#                          would silently turn the "external" copy into an internal one. For self-tests only.
#   TM_DEADLINE_SEC        whole-run time budget for apply, in seconds: a positive integer of at most 9 digits, default 3600.
#                          There is deliberately no "no limit" value; raise it for a bigger rescue. The deadline is fixed once,
#                          just before the first copy, and each rsync is killed when the budget runs out. A row whose copy was
#                          killed is rsync-timeout, a row never started is deadline-not-started; either one makes the run FAIL
#                          (the destination is kept, the receipt says "deadline: exceeded"). The clock counts whole seconds, so
#                          a kill can land up to a second late, and the re-inventory of a copy rsync already finished is not
#                          interrupted. Needs perl. 0, a negative number or a non-number is a usage error (exit 64), in dry too.
#
# Written inside the new directory:
#   <snapshot>/<rel>/        the copies (excluded names left out, see TM_EXCLUDES)
#   RESCUE-RESULTS.tsv       rel snapshot status files_src files_dst git unpushed_dst fsck parent_rel
#   RESCUE-RECEIPT.txt       result, deadline_sec, deadline (met|exceeded), rel_root and the exact exclude list, which
#                            tm-rescue-verify.sh reuses
#   RESCUE-LOG.txt           rsync output
#
# status "copied" is the only green value. Others: missing-in-backup, snapshot-unreadable, rsync-failed, rsync-timeout,
# deadline-not-started, inventory-failed, inventory-mismatch (files, directories or symlinks differ), empty-source,
# fsck-failed, and copied-worktree-parent-missing: a linked worktree keeps its history in its parent repository, so a worktree
# copy without that parent copied from the same snapshot in the same run loses its unpushed commits.
# Exit: 0 PASS, 1 FAIL (some row not green; the destination is kept), 2 refusal or bad input, 64 bad TM_DEADLINE_SEC.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tm-lib.sh
. "$here/tm-lib.sh"

mode=dry
case "${1:-}" in dry|apply) mode="$1"; shift ;; esac
# set-but-empty is as invalid as 0: the budget has no "unlimited" spelling. Leading zeros are decimal (10#), not octal.
deadline_sec="${TM_DEADLINE_SEC-3600}"
case "$deadline_sec" in
  ''|*[!0-9]*|??????????*) tm_usage "TM_DEADLINE_SEC must be a positive integer of at most 9 digits (seconds), got: '$deadline_sec'" ;;
esac
deadline_sec=$((10#$deadline_sec))
[[ "$deadline_sec" -gt 0 ]] || tm_usage "TM_DEADLINE_SEC must be a positive integer (seconds; there is no 'no limit' value), got: '$TM_DEADLINE_SEC'"
plan="${1:-${TM_PLAN:-}}"
[[ -n "$plan" && -f "$plan" ]] || tm_die "need a plan file: tm-rescue.sh [dry|apply] PLAN  (or set TM_PLAN)"

tm_init
tm_mktmp
trap 'rm -rf "$TM_TMP"' EXIT
tm_read_plan "$plan" "${TM_STAMP:-}" > "$TM_TMP/plan" || tm_die "plan $plan has unusable lines (listed above)"
[[ -s "$TM_TMP/plan" ]] || tm_die "plan $plan names no directories; refusing a vacuous run"

# every snapshot the plan names must be readable before anything is created
stamps="$(cut -f2 "$TM_TMP/plan" | LC_ALL=C sort -u)"
nstamps=0; newest=""
for s in $stamps; do
  tm_snap_home "$s" > /dev/null || tm_die "snapshot $s is not readable below $TM_ROOT (layout <stamp>.backup/<stamp>.backup/$TM_REL_ROOT)"
  nstamps=$((nstamps + 1)); newest="$s"
done
run_name="recovered-from-tm-$newest"
[[ "$nstamps" -gt 1 ]] && run_name="$run_name-and-earlier"

# ---- destination checks ----
# apply stops at the first refusal; dry collects them so the listing below is never hidden by, say, a tight disk
refusals=""
refuse() { if [[ "$mode" == apply ]]; then tm_die "$*"; fi; refusals="$refusals$*"$'\n'; }
# size of what will really be copied: excluded dependency directories are usually the biggest part of a tree
src_kb() { du -sk ${TM_DU_EXCL[@]+"${TM_DU_EXCL[@]}"} "$1" | awk '{print $1}'; }

DEST="${TM_DEST:-}"
if [[ -z "$DEST" && -n "${TM_DEST_ROOT:-}" ]]; then DEST="${TM_DEST_ROOT%/}/$run_name"; fi
need_kb=0; avail_kb="?"
while IFS=$'\t' read -r rel stamp <&3; do
  home="$(tm_snap_home "$stamp")"
  if [[ -d "$home/$rel" && ! -L "$home/$rel" ]]; then
    kb="$(src_kb "$home/$rel")"
    need_kb=$((need_kb + ${kb:-0}))
  fi
done 3< "$TM_TMP/plan"
if [[ -z "$DEST" ]]; then
  [[ "$mode" == apply ]] && tm_die "no destination: set TM_DEST_ROOT (an existing directory on the external volume) or TM_DEST (a new directory)"
else
  dparent="$(dirname "$DEST")"
  if [[ ! -d "$dparent" ]]; then
    refuse "destination parent does not exist (is the external volume mounted?): $dparent"
  else
    if [[ -e "$DEST" || -L "$DEST" ]]; then refuse "$DEST already exists; refusing to overwrite"; fi
    if [[ "${TM_ALLOW_INTERNAL_DEST:-0}" != 1 && "$(stat -f %d "$dparent" 2>/dev/null)" == "$(stat -f %d "$HOME" 2>/dev/null)" ]]; then
      refuse "destination is on the same device as \$HOME; rescue onto an external volume (TM_ALLOW_INTERNAL_DEST=1 overrides, for tests only)"
    fi
    avail_kb="$(df -k "$dparent" 2>/dev/null | awk 'NR==2{print $4}')"
    case "$avail_kb" in
      ''|*[!0-9]*) refuse "cannot read the free space of $dparent"; avail_kb="?" ;;
      *) if [[ "$need_kb" -gt "$avail_kb" ]]; then refuse "not enough free space on $dparent: need about $need_kb KiB, have $avail_kb KiB"; fi ;;
    esac
  fi
fi
command -v perl > /dev/null 2>&1 || refuse "perl is not available; the copy needs it to enforce TM_DEADLINE_SEC"

if [[ "$mode" == dry ]]; then
  tm_log "DRY RUN -- nothing is written (destination: ${DEST:-not given})"
  missing=0
  while IFS=$'\t' read -r rel stamp <&3; do
    home="$(tm_snap_home "$stamp")"
    src="$home/$rel"
    if [[ -L "$src" || ! -d "$src" ]]; then
      printf '%12s  %-9s %s  %s\n' MISSING - "$stamp" "$rel"; missing=$((missing + 1)); continue
    fi
    if [[ -d "$src/.git" ]]; then gk=repo; elif [[ -f "$src/.git" ]]; then gk=worktree; else gk=none; fi
    printf '%9s KiB  %-9s %s  %s\n' "$(src_kb "$src")" "$gk" "$stamp" "$rel"
  done 3< "$TM_TMP/plan"
  tm_log "would copy $(wc -l < "$TM_TMP/plan" | tr -d ' ') director(ies), about $need_kb KiB without the excluded names; free ${avail_kb} KiB; excludes: ${TM_EXCLUDES_EFFECTIVE:-none}"
  if [[ -n "$refusals" ]]; then
    while IFS= read -r r; do
      if [[ -n "$r" ]]; then echo "WOULD REFUSE: $r"; fi
    done <<< "$refusals"
    echo "RESULT: DRY -- apply would refuse (see above)"; exit 2
  fi
  [[ "$missing" == 0 ]] && exit 0
  echo "RESULT: DRY -- $missing director(ies) are missing in their backup; apply would FAIL those rows"; exit 1
fi

# ---- apply ----
umask 077
mkdir "$DEST" || tm_die "cannot create $DEST"
results="$DEST/RESCUE-RESULTS.tsv"
: > "$DEST/RESCUE-LOG.txt"
printf 'rel\tsnapshot\tstatus\tfiles_src\tfiles_dst\tgit\tunpushed_dst\tfsck\tparent_rel\n' > "$results"
# one deadline for the whole run, fixed before the first copy; every row is handed what is left of it
deadline_at=$((SECONDS + deadline_sec))
while IFS=$'\t' read -r rel stamp <&3; do
  left=$((deadline_at - SECONDS))
  if [[ "$left" -ge 1 ]]; then tm_log "copying $stamp/$rel (${left}s of the ${deadline_sec}s budget left)"
  else tm_log "TM_DEADLINE_SEC=$deadline_sec is used up; not starting $stamp/$rel"; fi
  tm_copy_one "$stamp" "$rel" "$DEST" "$left"
  printf '%s\n' "$TM_ROW" >> "$results"
done 3< "$TM_TMP/plan"

# A linked worktree is only rescued when its parent repository was copied in the same run from the same snapshot.
awk -F'\t' -v OFS='\t' '
  NR == FNR { if (FNR > 1 && $3 == "copied") ok[$2 SUBSEP $1] = 1; next }
  FNR == 1 { print; next }
  $3 == "copied" && $6 == "worktree" && !(($2 SUBSEP $9) in ok) { $3 = "copied-worktree-parent-missing" }
  { print }
' "$results" "$results" > "$results.new" && mv "$results.new" "$results"

rows="$(awk -F'\t' 'FNR>1' "$results" | wc -l | tr -d ' ')"
bad="$(awk -F'\t' 'FNR>1 && $3!="copied"' "$results" | wc -l | tr -d ' ')"
late="$(awk -F'\t' 'FNR>1 && ($3=="rsync-timeout" || $3=="deadline-not-started")' "$results" | wc -l | tr -d ' ')"
deadline=met; [[ "$late" == 0 ]] || deadline=exceeded
result=PASS; [[ "$bad" == 0 && "$rows" -gt 0 ]] || result=FAIL
{
  echo "tool: tm-rescue.sh"
  echo "result: $result"
  echo "created_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "deadline_sec: $deadline_sec"
  echo "deadline: $deadline"
  echo "rows: $rows"
  echo "rows_not_green: $bad"
  echo "rel_root: $TM_REL_ROOT"
  echo "excludes: $TM_EXCLUDES_EFFECTIVE"
  echo "snapshots: $(printf '%s' "$stamps" | tr '\n' ' ')"
  echo "policy: backup read-only; new destination directory; nothing deleted or modified in the source"
} > "$DEST/RESCUE-RECEIPT.txt"

tm_log "rows=$rows not_green=$bad  results: $results"
if [[ "$bad" != 0 ]]; then awk -F'\t' 'FNR>1 && $3!="copied" {printf "  NOT GREEN  %-34s %s/%s\n", $3, $2, $1}' "$results"; fi
if [[ "$deadline" == exceeded ]]; then echo "deadline: exceeded (TM_DEADLINE_SEC=$deadline_sec; $late row(s) killed or never started; the destination is kept)"; fi
if [[ "$result" == PASS ]]; then echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL (see $results)"; exit 1
