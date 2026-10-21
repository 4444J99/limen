#!/bin/bash
# Which repositories from a git-sweep survey have vanished from the Mac since, which of those carried work that exists
# nowhere else, and which Time Machine backup still has them? In apply mode, rescue the exposed ones.
#
# WHY: a sweep taken before a reset says what existed and what was unpushed; this re-checks the live disk, finds the newest
# backup that holds a COMPLETE copy of each vanished exposed checkout, and hands tm-rescue.sh a plan. The Mac and the
# backups are only read; tm-rescue.sh writes only into a NEW directory.
#
#   tm-vanished.sh dry   [SWEEP_TSV]   classify, write the report and a rescue plan; exit 1 if an exposed repo has no backup
#   tm-vanished.sh apply [SWEEP_TSV]   also run `tm-rescue.sh apply` on that plan (destination variables: see tm-rescue.sh)
#
# SWEEP_TSV (argument, or $TM_SWEEP_TSV) is the git.tsv from git-sweep.sh, read by column NAME: path, kind, remote, dirty,
# unpushed and stashes are required; branch and head_remote_branches are used when present.
#
# Environment (tm-lib.sh documents TM_ROOT, TM_REL_ROOT, TM_EXCLUDES):
#   TM_OUT         where the report and plan are written (default $TMPDIR/mac-exit-tm-vanished); rewritten each run
#   TM_STAMPS      backup stamps to search, NEWEST FIRST, space-separated (default: every <stamp>.backup below TM_ROOT)
#   TM_ALREADY     colon-separated list of earlier tm-rescue.sh destinations; directories they copied are not rescued again
#   TM_REAL_TSV    optional classify-git-sweep.py output; adds an informational in_real_list column
#
# A swept entry is "exposed" when its work may exist nowhere else: no origin remote, uncommitted changes, unpushed commits
# (an UNKNOWN count counts as exposed), stashes, or a detached HEAD (repo or worktree) that no remote branch contains --
# commits made there sit on no branch, so the unpushed count cannot see them. Rescue is cheap, so the rule leans towards
# including too much. The backup chosen is the newest one whose copy still has its .git (a
# backup taken mid-deletion can hold a husk). A linked worktree's history lives in its parent repository, so the parent is
# added to the plan too. Entries outside $HOME cannot be located in a backup and are reported as unrescuable.
#
# Writes TM_OUT/vanished.tsv (every vanished entry), TM_OUT/rescue-plan.tsv (rel snapshot reasons). Exit 0 when nothing is
# left unrescued; 1 when an exposed entry is in no backup or outside $HOME, or the rescue failed; 2 on bad input.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tm-lib.sh
. "$here/tm-lib.sh"

mode=dry
case "${1:-}" in dry|apply) mode="$1"; shift ;; esac
sweep="${1:-${TM_SWEEP_TSV:-}}"
[[ -n "$sweep" && -f "$sweep" ]] || tm_die "need a git-sweep TSV: tm-vanished.sh [dry|apply] SWEEP_TSV  (or set TM_SWEEP_TSV)"
out="${TM_OUT:-${TMPDIR:-/tmp}/mac-exit-tm-vanished}"
mkdir -p "$out" || tm_die "cannot create $out"

tm_init
tm_mktmp
trap 'rm -rf "$TM_TMP"' EXIT

# readable backups, newest first
ST_NAME=(); ST_HOME=()
if [[ -n "${TM_STAMPS:-}" ]]; then stamp_list="$(tr -s ' ' '\n' <<< "$TM_STAMPS")"; else stamp_list="$(tm_list_stamps)"; fi
while IFS= read -r s; do
  [[ -n "$s" ]] || continue
  tm_valid_stamp "$s" || tm_die "not a backup stamp (YYYY-MM-DD-HHMMSS): $s"
  if h="$(tm_snap_home "$s")"; then
    ST_NAME+=("$s"); ST_HOME+=("$h")
  else
    echo "WARN: backup $s is not readable below $TM_ROOT; skipped" >&2
  fi
done <<< "$stamp_list"
[[ "${#ST_NAME[@]}" -gt 0 ]] || tm_die "no readable backup below $TM_ROOT"

# directories earlier runs already copied
: > "$out/already.list"
if [[ -n "${TM_ALREADY:-}" ]]; then
  while IFS= read -r d; do
    [[ -n "$d" ]] || continue
    [[ -f "$d/RESCUE-RESULTS.tsv" ]] || tm_die "TM_ALREADY entry is not a tm-rescue.sh destination: $d"
    awk -F'\t' 'FNR>1 && $3=="copied" {print $1}' "$d/RESCUE-RESULTS.tsv" >> "$out/already.list"
  done <<< "$(tr ':' '\n' <<< "$TM_ALREADY")"
fi
: > "$out/real.list"
if [[ -n "${TM_REAL_TSV:-}" ]]; then
  [[ -f "$TM_REAL_TSV" ]] || tm_die "TM_REAL_TSV is not a file: $TM_REAL_TSV"
  awk -F'\t' 'NR>1 {print $1}' "$TM_REAL_TSV" > "$out/real.list"
fi

# normalise the sweep by column name; empty fields become "-" so tab-splitting in the shell cannot shift columns
awk -F'\t' -v OFS='\t' '
  function col(n) { return (n in c && $(c[n]) != "") ? $(c[n]) : "-" }
  NR == 1 {
    for (i = 1; i <= NF; i++) c[$i] = i
    split("path kind remote dirty unpushed stashes", need, " ")
    for (i = 1; i <= 6; i++) if (!(need[i] in c)) { print "sweep TSV lacks column: " need[i] > "/dev/stderr"; bad = 1 }
    if (bad) exit 2
    next
  }
  { print col("path"), col("kind"), col("branch"), col("remote"), col("dirty"), col("unpushed"), col("stashes"), col("head_remote_branches") }
' "$sweep" > "$out/sweep.norm" || tm_die "cannot read $sweep as a git-sweep TSV"
[[ -s "$out/sweep.norm" ]] || tm_die "$sweep has no data rows; refusing a vacuous run"

report="$out/vanished.tsv"; plan="$out/rescue-plan.tsv"
printf 'path\trel\tkind\tremote\tdirty\tunpushed\tstashes\texposed\treasons\tin_real_list\tsnapshot\talready_rescued\tplanned\n' > "$report"
: > "$out/plan.rows"; : > "$out/parents.rows"; : > "$out/unrescuable.rows"

total=0; vanished=0; exposed_n=0; rescuable=0; unrescuable=0; reasons=""
add_reason() { reasons="$reasons${reasons:+,}$1"; }

while IFS=$'\t' read -r path kind branch remote dirty unpushed stashes headrem <&3; do
  total=$((total + 1))
  if [[ -e "$path" || -L "$path" ]]; then continue; fi
  vanished=$((vanished + 1))

  reasons=""
  [[ "$remote" == NONE ]] && add_reason no-origin
  [[ "$dirty" != 0 ]] && add_reason dirty
  case "$unpushed" in 0) ;; '?') add_reason unpushed-unknown ;; *) add_reason unpushed ;; esac
  [[ "$stashes" != 0 ]] && add_reason stash
  [[ "$branch" == "(detached)" && "$headrem" == 0 ]] && add_reason detached-head-on-no-remote-branch
  exposed=no; [[ -n "$reasons" ]] && exposed=yes

  inreal="-"
  if [[ -n "${TM_REAL_TSV:-}" ]]; then inreal=no; grep -qxF -- "$path" "$out/real.list" && inreal=yes; fi

  rel="-"; found=outside-home
  case "$path" in
    "$HOME"/*)
      rel="${path#"$HOME"/}"; found=none; i=0
      while [[ "$i" -lt "${#ST_NAME[@]}" ]]; do
        if tm_backup_has "${ST_HOME[$i]}/$rel" "$kind"; then found="${ST_NAME[$i]}"; break; fi
        i=$((i + 1))
      done ;;
  esac
  already=no
  if [[ "$rel" != "-" ]] && grep -qxF -- "$rel" "$out/already.list"; then already=yes; fi

  planned=no
  if [[ "$exposed" == yes ]]; then
    exposed_n=$((exposed_n + 1))
    if [[ "$already" == no ]]; then
      case "$found" in
        none|outside-home)
          unrescuable=$((unrescuable + 1))
          printf '%s\t%s\t%s\n' "$path" "$reasons" "$found" >> "$out/unrescuable.rows" ;;
        *)
          rescuable=$((rescuable + 1)); planned=yes
          printf '%s\t%s\t%s\t%s\n' "$rel" "$found" "$reasons" "$kind" >> "$out/plan.rows" ;;
      esac
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$path" "$rel" "$kind" "$remote" "$dirty" "$unpushed" "$stashes" "$exposed" "${reasons:--}" "$inreal" "$found" "$already" "$planned" >> "$report"
done 3< "$out/sweep.norm"

# A linked worktree keeps its history in its parent repository: copy the parent in the same run, from the same backup.
parents=0
plan_keys=$'\n'"$(cut -f1,2 "$out/plan.rows")"$'\n'
while IFS=$'\t' read -r rel stamp _why kind <&3; do
  [[ "$kind" == worktree ]] || continue
  home="$(tm_snap_home "$stamp")"
  prel="$(tm_worktree_parent "$home/$rel" "$home")"
  if [[ -z "$prel" ]]; then
    echo "WARN: cannot resolve the parent repository of worktree $rel; its copy will be reported as copied-worktree-parent-missing"; continue
  fi
  case "$plan_keys" in *$'\n'"$prel"$'\t'"$stamp"$'\n'*) continue ;; esac
  if tm_backup_has "$home/$prel" repo; then
    printf '%s\t%s\t%s\t%s\n' "$prel" "$stamp" "parent-of-worktree" repo >> "$out/parents.rows"; parents=$((parents + 1))
    plan_keys="$plan_keys$prel"$'\t'"$stamp"$'\n'
  else
    echo "WARN: parent repository $prel of worktree $rel is not complete in backup $stamp; the worktree copy will be reported as copied-worktree-parent-missing"
  fi
done 3< "$out/plan.rows"

printf 'rel\tsnapshot\treasons\n' > "$plan"
cut -f1-3 "$out/plan.rows" "$out/parents.rows" >> "$plan"
planned_n="$(awk 'FNR>1' "$plan" | wc -l | tr -d ' ')"

echo "swept entries: $total; vanished from the Mac: $vanished; carrying exposed work: $exposed_n"
echo "exposed, not yet rescued, present in a backup: $rescuable (+$parents parent repo(s) for linked worktrees); exposed but UNRESCUABLE: $unrescuable"
echo "== exposed and NOT already rescued =="
awk -F'\t' 'NR>1 && $8=="yes" && $12=="no" {printf "  %-16s %-20s %s\n", $11, $3, $1}' "$report"
echo "report: $report"
echo "plan:   $plan ($planned_n row(s))"
if [[ "$unrescuable" != 0 ]]; then
  echo "== UNRESCUABLE: exposed, but in no readable backup or outside \$HOME =="
  awk -F'\t' '{printf "  %-12s %s  (%s)\n", $3, $1, $2}' "$out/unrescuable.rows"
fi

if [[ "$mode" == dry ]]; then
  [[ "$unrescuable" == 0 ]] && exit 0
  echo "RESULT: DRY -- $unrescuable exposed entr(ies) cannot be rescued from any readable backup"; exit 1
fi

rc=0
if [[ "$planned_n" -gt 0 ]]; then
  export TM_ROOT TM_REL_ROOT
  "${BASH:-/bin/bash}" "$here/tm-rescue.sh" apply "$plan"; rc=$?
else
  echo "nothing to rescue: no exposed, un-rescued entry is present in a backup"
fi
if [[ "$rc" != 0 ]]; then exit "$rc"; fi
if [[ "$unrescuable" != 0 ]]; then echo "RESULT: FAIL -- $unrescuable exposed entr(ies) were not rescuable (listed above)"; exit 1; fi
echo "RESULT: PASS"; exit 0
