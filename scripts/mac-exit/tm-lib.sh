#!/bin/bash
# Shared helpers for the tm-*.sh Time Machine rescue tools. SOURCED by them, never run directly.
#
# WHY a library: the copier, the vanished-repo planner and the verifier must agree on three things or the proof means
# nothing -- where a backup keeps the user's files, which regenerable directories are left out, and how a tree is
# fingerprinted. Three hand-copied exclude lists is how a verifier ends up checking a different set than the copier wrote.
#
# Parameters (environment; each tool's header says which ones it reads):
#   TM_ROOT      directory holding the <YYYY-MM-DD-HHMMSS>.backup entries. Default: the single volume directory below
#                /Volumes/.timemachine when there is exactly one. A snapshot mounted by tm-mount-snapshot.sh works too:
#                point TM_ROOT at its mount point (both layouts are probed, see tm_snap_home).
#   TM_REL_ROOT  backup-relative directory that corresponds to $HOME. Default: "Data" followed by $HOME, the layout of a
#                macOS Time Machine backup of the Data volume.
#   TM_EXCLUDES  space-separated plain names left out of every copy and every comparison. Default: node_modules .venv venv
#                __pycache__ .pytest_cache .ruff_cache .mypy_cache .next (regenerable). Set it empty to copy everything.
#
# Host constraints honoured here: /bin/bash 3.2 (no mapfile, no associative arrays, empty arrays expand through
# ${a[@]+"${a[@]}"} under set -u), BSD or bfs find (-xdev only; no -printf, no -x), openrsync 2.6.9 (only -a and
# --exclude=NAME are used), BSD du (-I NAME), BSD stat (-f %d), shasum or sha256sum. macOS is the target platform.

unset CDPATH GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
export GIT_OPTIONAL_LOCKS=0 GIT_NO_LAZY_FETCH=1 GIT_TERMINAL_PROMPT=0

TM_DEFAULT_EXCLUDES="node_modules .venv venv __pycache__ .pytest_cache .ruff_cache .mypy_cache .next"

tm_log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
tm_die() { printf 'FAIL: %s\n' "$*" >&2; exit 2; }
tm_usage() { printf 'USAGE: %s\n' "$*" >&2; exit 64; }

# tm_init -- resolve the TM_* parameters; builds TM_PRUNE (find), TM_RSYNC_EXCL (rsync), TM_DU_EXCL (BSD du -I),
# TM_EXCLUDES_EFFECTIVE and TM_SHA.
tm_init() {
  local d n=0 only="" name first=1
  [[ -n "${HOME:-}" ]] || tm_die "HOME is not set"
  TM_REL_ROOT="${TM_REL_ROOT:-Data$HOME}"
  TM_REL_ROOT="${TM_REL_ROOT#/}"; TM_REL_ROOT="${TM_REL_ROOT%/}"
  if [[ -z "${TM_ROOT:-}" ]]; then
    for d in /Volumes/.timemachine/*/; do
      if [[ -d "$d" ]]; then n=$((n + 1)); only="${d%/}"; fi
    done
    if [[ "$n" == 1 ]]; then TM_ROOT="$only"; fi
  fi
  [[ -n "${TM_ROOT:-}" ]] || tm_die "TM_ROOT is not set and /Volumes/.timemachine does not hold exactly one backup volume"
  TM_ROOT="${TM_ROOT%/}"
  [[ -d "$TM_ROOT" ]] || tm_die "TM_ROOT is not a directory: $TM_ROOT"

  TM_EXCLUDE_NAMES=(); TM_PRUNE=(); TM_RSYNC_EXCL=(); TM_DU_EXCL=(); TM_EXCLUDES_EFFECTIVE=""
  read -r -a TM_EXCLUDE_NAMES <<< "${TM_EXCLUDES-$TM_DEFAULT_EXCLUDES}"
  for name in ${TM_EXCLUDE_NAMES[@]+"${TM_EXCLUDE_NAMES[@]}"}; do
    case "$name" in
      */*|*'*'*|*'?'*|*'['*|*']'*|*\\*) tm_die "TM_EXCLUDES entries must be plain names, got: $name" ;;
    esac
    if [[ "$first" == 1 ]]; then TM_PRUNE=( \( ); first=0; else TM_PRUNE+=( -o ); fi
    TM_PRUNE+=( -name "$name" )
    TM_RSYNC_EXCL+=( "--exclude=$name" )
    TM_DU_EXCL+=( -I "$name" )
    TM_EXCLUDES_EFFECTIVE="$TM_EXCLUDES_EFFECTIVE${TM_EXCLUDES_EFFECTIVE:+ }$name"
  done
  if [[ "$first" == 0 ]]; then TM_PRUNE+=( \) -prune -o ); fi

  if command -v shasum >/dev/null 2>&1; then TM_SHA=(shasum -a 256)
  elif command -v sha256sum >/dev/null 2>&1; then TM_SHA=(sha256sum)
  else tm_die "neither shasum nor sha256sum is available"; fi
  return 0
}

# tm_mktmp -- per-run scratch directory in TM_TMP (callers install their own cleanup trap).
tm_mktmp() { TM_TMP="$(mktemp -d "${TMPDIR:-/tmp}/tm-tools.XXXXXX")" || tm_die "cannot create a temp directory"; }

tm_valid_stamp() {
  case "$1" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]) return 0 ;;
  esac
  return 1
}

# tm_list_stamps -- backup stamps present under TM_ROOT, newest first.
tm_list_stamps() {
  local d b
  for d in "$TM_ROOT"/????-??-??-??????.backup; do
    [[ -d "$d" ]] || continue
    b="${d##*/}"; b="${b%.backup}"
    if tm_valid_stamp "$b"; then printf '%s\n' "$b"; fi
  done | LC_ALL=C sort -r
}

# tm_snap_home STAMP -- print the directory that corresponds to $HOME inside backup STAMP; non-zero when it is unreadable.
# Two layouts are probed: the one macOS exposes under /Volumes/.timemachine (<stamp>.backup/<stamp>.backup/<rel root>,
# the outer directory being the snapshot mount) and a snapshot mounted by hand at TM_ROOT (<stamp>.backup/<rel root>).
tm_snap_home() {
  local s="$1" c
  for c in "$TM_ROOT/$s.backup/$s.backup/$TM_REL_ROOT" "$TM_ROOT/$s.backup/$TM_REL_ROOT"; do
    if [[ -d "$c" ]]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}

# tm_backup_has DIR KIND -- does DIR look like a COMPLETE git checkout inside a backup? A backup taken mid-deletion can hold
# a directory whose .git is already gone; choosing it would "rescue" a husk while an older backup has the real thing.
tm_backup_has() {
  local d="$1" kind="$2"
  [[ -d "$d" && ! -L "$d" ]] || return 1
  case "$kind" in
    repo) [[ -f "$d/.git/HEAD" ]] ;;
    *)    [[ -e "$d/.git" ]] ;;
  esac
}

# tm_read_plan FILE DEFAULT_STAMP -- validate a rescue plan and print "rel<TAB>snapshot" lines (deduplicated).
# A line is "rel<TAB>snapshot[<TAB>anything]" or a bare "rel" (then DEFAULT_STAMP applies). rel is relative to $HOME, or an
# absolute path below it; "..", "." components and absolute paths outside $HOME are refused. Returns 1 on any bad line.
tm_read_plan() {
  local f="$1" dflt="${2:-}" line rel stamp rest lineno=0 bad=0 seen=$'\n'
  while IFS= read -r line || [[ -n "$line" ]]; do
    lineno=$((lineno + 1))
    case "$line" in
      ''|'#'*) continue ;;
      rel$'\t'snapshot*) continue ;;
    esac
    rel="${line%%$'\t'*}"
    if [[ "$line" == *$'\t'* ]]; then
      rest="${line#*$'\t'}"; stamp="${rest%%$'\t'*}"
    else
      stamp="$dflt"
    fi
    while [[ "$rel" == */ ]]; do rel="${rel%/}"; done
    # shellcheck disable=SC2016  # the message names the variable on purpose
    case "$rel" in
      "$HOME"/*) rel="${rel#"$HOME"/}" ;;
      /*) printf 'plan line %s: absolute path outside $HOME: %s\n' "$lineno" "$rel" >&2; bad=1; continue ;;
    esac
    case "/$rel/" in
      //|*/../*|*/./*|*//*) printf 'plan line %s: unsafe or empty path: %s\n' "$lineno" "$rel" >&2; bad=1; continue ;;
    esac
    if ! tm_valid_stamp "$stamp"; then
      printf 'plan line %s: snapshot must look like YYYY-MM-DD-HHMMSS, got: %s\n' "$lineno" "$stamp" >&2; bad=1; continue
    fi
    case "$seen" in *$'\n'"$rel"$'\t'"$stamp"$'\n'*) continue ;; esac
    seen="$seen$rel"$'\t'"$stamp"$'\n'
    printf '%s\t%s\n' "$rel" "$stamp"
  done < "$f"
  return "$bad"
}

# tm_inventory DIR ERRFILE -- sorted "d<TAB>path", "f<TAB>path" and "l<TAB>path<TAB>target" lines for everything below DIR
# (excluded names pruned). Sockets, fifos and device nodes carry no data and are ignored. Errors append to ERRFILE; the
# caller treats a non-empty ERRFILE as failure, so an unreadable entry can never read as "absent on both sides".
tm_inventory() {
  local dir="$1" err="$2"
  (
    set -o pipefail
    cd "$dir" || exit 1
    find . -xdev ${TM_PRUNE[@]+"${TM_PRUNE[@]}"} \( -type d -o -type f -o -type l \) ! -path . -print0 2>>"$err" |
    while IFS= read -r -d '' p; do
      if [[ -L "$p" ]]; then printf 'l\t%s\t%s\n' "$p" "$(readlink "$p")"
      elif [[ -d "$p" ]]; then printf 'd\t%s\n' "$p"
      else printf 'f\t%s\n' "$p"; fi
    done | LC_ALL=C sort
  )
}

# tm_hash_manifest DIR ERRFILE -- sorted "<sha256>  ./path" lines for the regular files below DIR (excluded names pruned).
# Non-zero when a file could not be listed or read.
tm_hash_manifest() {
  local dir="$1" err="$2"
  (
    set -o pipefail
    cd "$dir" || exit 1
    find . -xdev ${TM_PRUNE[@]+"${TM_PRUNE[@]}"} -type f -print0 2>>"$err" | LC_ALL=C sort -z | xargs -0 -r "${TM_SHA[@]}" 2>>"$err"
  )
}

# tm_git_probe DIR -- sets TM_GIT_KIND (repo|worktree|none), TM_GIT_UNPUSHED and TM_GIT_FSCK for a COPY of a checkout.
# A linked worktree has a .git FILE: its history lives in the parent repository, so it is only labelled here.
tm_git_probe() {
  local d="$1"
  TM_GIT_KIND=none; TM_GIT_UNPUSHED="-"; TM_GIT_FSCK="-"
  if [[ -d "$d/.git" && ! -L "$d/.git" ]]; then
    TM_GIT_KIND=repo
    TM_GIT_UNPUSHED="$(git -C "$d" rev-list --count --branches --not --remotes 2>/dev/null)" || TM_GIT_UNPUSHED="?"
    if git -C "$d" fsck --connectivity-only >/dev/null 2>&1; then TM_GIT_FSCK=ok; else TM_GIT_FSCK=FAILED; fi
  elif [[ -f "$d/.git" ]]; then
    TM_GIT_KIND=worktree
  fi
}

# tm_worktree_parent SRCDIR SNAPHOME -- print the parent repository of a linked worktree as a path relative to $HOME (the
# backed-up home), or nothing when it cannot be resolved. The pointer is absolute on the machine that wrote it, or relative.
tm_worktree_parent() {
  local d="$1" snap="$2" ptr common prefix
  ptr="$(sed -n '1s/^gitdir: //p' "$d/.git" 2>/dev/null)"
  case "$ptr" in */worktrees/*) ;; *) return 0 ;; esac
  case "$ptr" in
    /*) prefix="$HOME" ;;
    *)  ptr="$(cd -P "$d" 2>/dev/null && cd -P "$ptr" 2>/dev/null && pwd -P)" || return 0
        prefix="$(cd -P "$snap" 2>/dev/null && pwd -P)" || return 0 ;;
  esac
  common="${ptr%/worktrees/*}"
  case "$common" in */.git) common="${common%/.git}" ;; esac
  case "$common" in "$prefix"/*) printf '%s\n' "${common#"$prefix"/}" ;; esac
  return 0
}

# tm_run_within SECONDS CMD... -- run CMD with a hard wall-clock limit. The alarm survives the exec, so CMD itself is killed
# (SIGALRM) and the status is 142; a CMD that ends normally keeps its own status, and one that cannot be started is 127 (a
# failed perl exec would otherwise fall off the end of the script and read as success). Needs perl; same idiom as nongit-homing.sh.
TM_RC_TIMEOUT=142
tm_run_within() { perl -e 'alarm shift; exec @ARGV or do { print STDERR "cannot run $ARGV[0]: $!\n"; exit 127 }' "$@"; }

# tm_copy_one STAMP REL DEST BUDGET_SEC -- copy backup STAMP's REL into DEST/STAMP/REL, then re-inventory both sides and probe git.
# Sets TM_ROW (the RESCUE-RESULTS.tsv line) and TM_ROW_STATUS; "copied" is the only green status. The backup is only read.
# Needs TM_TMP and a log file DEST/RESCUE-LOG.txt that receives rsync's output. BUDGET_SEC is the time left in the caller's
# whole-run budget, in whole seconds, and is required (there is no "unlimited" call): below 1 the copy is not started
# (deadline-not-started); otherwise rsync is killed when it runs out (rsync-timeout) and the re-inventory is skipped, since a
# killed copy is partial by definition and walking the trees would spend the time the budget just ran out of.
tm_copy_one() {
  local stamp="$1" rel="$2" dest="$3" budget="${4:?tm_copy_one needs the remaining time budget in seconds}"
  local home="" src="" dst="" status=copied fs="-" fd="-" parent="-" ok=1 ptr rc=0
  TM_GIT_KIND=none; TM_GIT_UNPUSHED="-"; TM_GIT_FSCK="-"
  if [[ "$budget" -lt 1 ]]; then
    status=deadline-not-started
  elif ! home="$(tm_snap_home "$stamp")"; then
    status=snapshot-unreadable
  else
    src="$home/$rel"; dst="$dest/$stamp/$rel"
    if [[ -L "$src" || ! -d "$src" ]]; then
      status=missing-in-backup
    elif ! mkdir -p "$dst"; then
      status=mkdir-failed
    else
      tm_run_within "$budget" rsync -a ${TM_RSYNC_EXCL[@]+"${TM_RSYNC_EXCL[@]}"} "$src/" "$dst/" >> "$dest/RESCUE-LOG.txt" 2>&1 || rc=$?
      if [[ "$rc" == "$TM_RC_TIMEOUT" ]]; then
        status=rsync-timeout
      else
        [[ "$rc" == 0 ]] || status=rsync-failed
        : > "$TM_TMP/inv.err"
        tm_inventory "$src" "$TM_TMP/inv.err" > "$TM_TMP/inv.src" || ok=0
        tm_inventory "$dst" "$TM_TMP/inv.err" > "$TM_TMP/inv.dst" || ok=0
        [[ -s "$TM_TMP/inv.err" ]] && ok=0
        if [[ "$ok" == 0 ]]; then
          [[ "$status" == copied ]] && status=inventory-failed
        else
          fs="$(awk -F'\t' '$1=="f"{n++} END{print n+0}' "$TM_TMP/inv.src")"
          fd="$(awk -F'\t' '$1=="f"{n++} END{print n+0}' "$TM_TMP/inv.dst")"
          if ! cmp -s "$TM_TMP/inv.src" "$TM_TMP/inv.dst"; then
            [[ "$status" == copied ]] && status=inventory-mismatch
          fi
          if [[ "$fs" == 0 ]]; then
            [[ "$status" == copied ]] && status=empty-source
          fi
        fi
        tm_git_probe "$dst"
        if [[ "$TM_GIT_FSCK" == FAILED && "$status" == copied ]]; then status=fsck-failed; fi
        if [[ "$TM_GIT_KIND" == worktree ]]; then
          ptr="$(tm_worktree_parent "$src" "$home")"
          if [[ -n "$ptr" ]]; then parent="$ptr"; fi
        fi
      fi
    fi
  fi
  # outputs for the caller (this file is sourced)
  # shellcheck disable=SC2034
  TM_ROW_STATUS="$status"
  # shellcheck disable=SC2034
  printf -v TM_ROW '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
    "$rel" "$stamp" "$status" "$fs" "$fd" "$TM_GIT_KIND" "$TM_GIT_UNPUSHED" "$TM_GIT_FSCK" "$parent"
  return 0
}
