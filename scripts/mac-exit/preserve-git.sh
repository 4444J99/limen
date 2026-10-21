#!/usr/bin/env bash
# preserve-git.sh <real.tsv> <dest-root> <dry|apply>
#
# Preserves every real-exposure git entry listed in real.tsv onto an external volume so the work
# survives a Mac erase. Strictly read-only toward every repository (no fetch/gc/prune/commit/
# checkout/stash/index refresh); the only writes are into the brand-new run directory (apply) or
# the scratch directory (both modes; see PRESERVE_SCRATCH).
#
# Run directory layout (apply):
#   MANIFEST.tsv                       one row per item: kind status slug source file bytes sha256 entries note
#   bundles/<slug>.bundle              git bundle --all of each unique git common dir (all refs, tags, remotes, refs/stash)
#   bundles/<slug>.head.bundle         HEAD not reachable from any remote, for every detached-HEAD row
#   bundles/<slug>.gitdir.tar          raw copy of a git dir where a bundle cannot work: partial clones (the network is never
#                                      used: GIT_NO_LAZY_FETCH=1), unborn HEAD with staged blobs, or a failed bundle
#   dirty/<slug>.tracked.patch         git diff --binary HEAD for rows with dirty>0
#   dirty/<slug>.untracked.tar         untracked, non-ignored files of those rows
#   dirty/<slug>.staged.tar            unborn-HEAD rows only: every path in the index (git ls-files --cached)
#   dirty/<slug>.orphan-tree.tar       DEVIATION: raw working tree of rows that exist but whose gitfile no longer resolves
#   dirty/<cslug>.stashN.patch         stash entries below refs/stash (a bundle --all keeps only the top entry)
#   dirty/<cslug>.stash-reflog.txt     the refs/stash reflog (index, sha, subject)
#   dirty/skipped.txt                  reason, slug, path, bytes: files over 2 GiB, nested-repo entries, vanished files
#   dirty/credential-skipped.txt       tag, slug, path, bytes: credential-pattern files left out (path and size only)
#   preserve-git.sh, INPUT.real.tsv    provenance copies; run.log is the transcript (not in MANIFEST)
#
# Env knobs: PRESERVE_MIN_FREE_GIB (default 100), PRESERVE_SOFT_DEADLINE_SEC (default 1650),
# PRESERVE_SCRATCH (default ${TMPDIR:-/tmp}/preserve-git-scratch).

set -u
set -o pipefail
export GIT_OPTIONAL_LOCKS=0
export COPYFILE_DISABLE=1
export LC_ALL=C
# Never reach the network: a partial clone (promisor remote) would otherwise lazy-fetch missing blobs into the repo
# during `git diff` / `git bundle`, which is a write into the repository. Learned the hard way in the first run.
export GIT_NO_LAZY_FETCH=1
export GIT_TERMINAL_PROMPT=0

usage() { echo "usage: $0 <real.tsv> <dest-root> <dry|apply>" >&2; exit 64; }
[ $# -eq 3 ] || usage
TSV=$1
DEST=$2
MODE=$3
case "$MODE" in dry | apply) ;; *) usage ;; esac
[ -f "$TSV" ] || { echo "no such tsv: $TSV" >&2; exit 66; }

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
SELF="$SELF_DIR/$(basename "$0")"
HOME_DIR=${HOME:?HOME unset}
MIN_FREE_GIB=${PRESERVE_MIN_FREE_GIB:-100}
SOFT_DEADLINE_SEC=${PRESERVE_SOFT_DEADLINE_SEC:-1650}
MAX_FILE_BYTES=$((2 * 1024 * 1024 * 1024))
START_EPOCH=$(date +%s)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SCR="${PRESERVE_SCRATCH:-${TMPDIR:-/tmp}/preserve-git-scratch}/$MODE-$STAMP"
mkdir -p "$SCR" || { echo "cannot create scratch $SCR" >&2; exit 73; }

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }

# Every git call: no fsmonitor daemon, no pager/colour, never an index refresh (GIT_OPTIONAL_LOCKS=0).
G() { command git -c core.fsmonitor=false -c color.ui=false -c core.pager=cat "$@"; }

# ---------------------------------------------------------------------------------------------
# python helper (stdlib only): sha256 without populating the page cache, credential/size filters
# ---------------------------------------------------------------------------------------------
HELPER="$SCR/helper.py"
cat > "$HELPER" <<'PY'
import fnmatch
import hashlib
import os
import stat
import sys

F_NOCACHE = 48  # darwin fcntl: do not populate the unified buffer cache while reading

CRED_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "*.keychain", "*.keychain-db", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".pgpass",
    "credentials", "credentials.json", "service-account*.json", "*.token", ".token", "token",
    "tokens.json", "secrets.json", "secrets.yaml", "secrets.yml", "*.secret",
]
CRED_DIRS = {".ssh", ".gnupg", ".aws", ".1password", "1password", "keychains", "private_keys"}
SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub")


def sha256_file(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            import fcntl
            fcntl.fcntl(fd, F_NOCACHE, 1)
        except Exception:
            pass
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            h.update(block)
    finally:
        os.close(fd)
    return h.hexdigest()


def is_cred(rel):
    parts = [p for p in rel.lower().split("/") if p]
    if not parts:
        return False
    for d in parts[:-1]:
        if d in CRED_DIRS:
            return True
    base = parts[-1]
    if base.endswith(SAFE_SUFFIXES):
        return False
    return any(fnmatch.fnmatchcase(base, pat) for pat in CRED_PATTERNS)


def read_nul(path):
    with open(path, "rb") as fh:
        return [n for n in fh.read().split(b"\0") if n]


def esc(raw):
    if raw.startswith(b"./"):
        raw = raw[2:]
    s = raw.decode("utf-8", "surrogateescape")
    s = s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
    return s.encode("utf-8", "surrogateescape")


def cmd_sha256(path):
    print(sha256_file(path))


def cmd_cred_names(repo, inp, out, tag, slug, credlist):
    # Tracked-change names: write credential-pattern ones (NUL separated) to `out`, log path+size only.
    repo_b = os.fsencode(repo)
    count = 0
    with open(out, "wb") as of, open(credlist, "ab") as cf:
        for n in read_nul(inp):
            if not is_cred(n.decode("utf-8", "replace")):
                continue
            try:
                size = os.lstat(os.path.join(repo_b, n)).st_size
            except OSError:
                size = 0
            of.write(n + b"\0")
            cf.write(tag.encode() + b"\t" + slug.encode() + b"\t" + esc(n) + b"\t" + str(size).encode() + b"\n")
            count += 1
    print(count)


def cmd_filter_untracked(repo, inp, keep, skipped, credlist, slug, maxb):
    repo_b = os.fsencode(repo)
    maxb = int(maxb)
    slug_b = slug.encode()
    kc = kb = big = nested = special = cred = credb = gone = 0
    with open(keep, "wb") as kf, open(skipped, "ab") as sf, open(credlist, "ab") as cf:
        for n in read_nul(inp):
            if n.endswith(b"/"):
                # a nested git repository; it is preserved by its own bundle when it is a real-exposure row
                nested += 1
                sf.write(b"nested-repo\t" + slug_b + b"\t" + esc(n) + b"\t0\n")
                continue
            try:
                st = os.lstat(os.path.join(repo_b, n))
            except OSError:
                gone += 1
                sf.write(b"vanished-file\t" + slug_b + b"\t" + esc(n) + b"\t0\n")
                continue
            if is_cred(n.decode("utf-8", "replace")):
                cred += 1
                credb += st.st_size
                cf.write(b"untracked-tar\t" + slug_b + b"\t" + esc(n) + b"\t" + str(st.st_size).encode() + b"\n")
                continue
            if stat.S_ISREG(st.st_mode):
                if st.st_size > maxb:
                    big += 1
                    sf.write(b"over-2GiB\t" + slug_b + b"\t" + esc(n) + b"\t" + str(st.st_size).encode() + b"\n")
                    continue
            elif not stat.S_ISLNK(st.st_mode):
                special += 1
                sf.write(b"special-file\t" + slug_b + b"\t" + esc(n) + b"\t0\n")
                continue
            kf.write(n + b"\0")
            kc += 1
            kb += st.st_size
    print(kc, kb, big, nested, special, cred, credb, gone)


def main(argv):
    cmd, args = argv[1], argv[2:]
    {"sha256": cmd_sha256, "cred-names": cmd_cred_names, "filter-untracked": cmd_filter_untracked}[cmd](*args)


main(sys.argv)
PY

# ---------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------
sha256() { python3 -I "$HELPER" sha256 "$1" 2> /dev/null; }

slugify() {
  # path relative to $HOME with / -> __, truncated to 150 chars, plus -<first 8 hex of sha256(full path)>
  local p=$1 rel h
  case "$p" in
    "$HOME_DIR"/*) rel=${p#"$HOME_DIR"/} ;;
    *) rel=${p#/} ;;
  esac
  rel=${rel//\//__}
  rel=${rel:0:150}
  h=$(printf '%s' "$p" | shasum -a 256)
  printf '%s-%s' "$rel" "${h:0:8}"
}

clean_note() { printf '%s' "$1" | tr '\t\n\r' '   ' | cut -c1-300; }
first_line() { head -n 1 "$1" 2> /dev/null; }
past_deadline() { [ $(($(date +%s) - START_EPOCH)) -ge "$SOFT_DEADLINE_SEC" ]; }

# manifest <kind> <status> <slug> <source> <relfile> <entries> <note>   (apply mode only)
manifest() {
  local kind=$1 status=$2 slug=$3 src=$4 rel=$5 entries=$6 note=$7 bytes=0 sha=""
  if [ -n "$rel" ] && [ -f "$RUN/$rel" ]; then
    bytes=$(stat -f %z "$RUN/$rel")
    sha=$(sha256 "$RUN/$rel")
    if [ -z "$sha" ]; then
      status=failed
      note="sha256 read-back failed; $note"
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kind" "$status" "$slug" "$src" "$rel" "$bytes" "$sha" "$entries" "$(clean_note "$note")" >> "$MANIFEST"
  log "item $kind $status $slug bytes=$bytes entries=$entries"
}

est_bytes() { # estimated bundle bytes from count-objects (loose + packed, KiB)
  local out
  out=$(G --git-dir="$1" count-objects -v 2> /dev/null) || { echo 0; return; }
  printf '%s\n' "$out" | awk -F': ' '$1=="size"||$1=="size-pack"{s+=$2} END{printf "%d", s*1024}'
}

# ---------------------------------------------------------------------------------------------
# destination checks and run directory
# ---------------------------------------------------------------------------------------------
existing=$DEST
while [ ! -d "$existing" ]; do existing=$(dirname "$existing"); done
AVAIL_KIB=$(df -Pk "$existing" | awk 'NR==2{print $4}')
NEED_KIB=$((MIN_FREE_GIB * 1024 * 1024))
log "mode=$MODE tsv=$TSV dest=$DEST free=${AVAIL_KIB}KiB need=${NEED_KIB}KiB scratch=$SCR"

RUN=""
MANIFEST=""
if [ "$MODE" = apply ]; then
  if [ "$AVAIL_KIB" -lt "$NEED_KIB" ]; then
    echo "refusing: only ${AVAIL_KIB} KiB free on the destination volume, need ${NEED_KIB} KiB (${MIN_FREE_GIB} GiB)" >&2
    exit 75
  fi
  mkdir -p "$DEST" || { echo "cannot create dest-root $DEST" >&2; exit 73; }
  RUN="$DEST/run-$STAMP"
  mkdir "$RUN" || { echo "refusing: run directory $RUN already exists or cannot be created" >&2; exit 73; }
  mkdir "$RUN/bundles" "$RUN/dirty" || exit 73
  exec > >(tee -a "$RUN/run.log") 2>&1
  MANIFEST="$RUN/MANIFEST.tsv"
  printf 'item_kind\tstatus\tslug\tsource\tfile\tbytes\tsha256\tentries\tnote\n' > "$MANIFEST"
  : > "$RUN/dirty/skipped.txt"
  : > "$RUN/dirty/credential-skipped.txt"
  cp "$SELF" "$RUN/preserve-git.sh"
  cp "$TSV" "$RUN/INPUT.real.tsv"
  log "run directory $RUN"
  manifest provenance ok preserve-git.sh "$SELF" preserve-git.sh "" "script copy"
  manifest provenance ok INPUT.real.tsv "$TSV" INPUT.real.tsv "" "input copy"
  SKIPPED="$RUN/dirty/skipped.txt"
  CREDLIST="$RUN/dirty/credential-skipped.txt"
else
  SKIPPED="$SCR/skipped.txt"
  CREDLIST="$SCR/credential-skipped.txt"
  : > "$SKIPPED"
  : > "$CREDLIST"
  log "dry mode: $([ "$AVAIL_KIB" -ge "$NEED_KIB" ] && echo "free-space check would pass" || echo "free-space check would FAIL")"
fi

# ---------------------------------------------------------------------------------------------
# phase 0: resolve rows to unique git common dirs
# ---------------------------------------------------------------------------------------------
tr '\t' '\037' < "$TSV" | tail -n +2 > "$SCR/rows.us"
: > "$SCR/rowinfo.tsv"     # path kind branch remote dirty common
: > "$SCR/orphans.tsv"     # path slug  (exist on disk, git cannot resolve a common dir)
NROWS=0
NVANISHED=0
NFAILED_RESOLVE=0
while IFS=$'\037' read -r -u 3 path kind branch remote dirty unpushed stashes reasons; do
  [ -n "$path" ] || continue
  NROWS=$((NROWS + 1))
  case "$dirty" in '' | *[!0-9]*) dirty=0 ;; esac
  rslug=$(slugify "$path")
  if [ ! -d "$path" ]; then
    NVANISHED=$((NVANISHED + 1))
    log "row vanished: $path"
    if [ "$MODE" = apply ]; then manifest row vanished "$rslug" "$path" "" "" "path no longer exists${PRESERVE_VANISHED_NOTE:+; $PRESERVE_VANISHED_NOTE}"; fi
    continue
  fi
  common=$(G -C "$path" rev-parse --path-format=absolute --git-common-dir 2> "$SCR/resolve.err")
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$common" ]; then
    NFAILED_RESOLVE=$((NFAILED_RESOLVE + 1))
    log "row unresolved: $path ($(first_line "$SCR/resolve.err"))"
    printf '%s\t%s\n' "$path" "$rslug" >> "$SCR/orphans.tsv"
    if [ "$MODE" = apply ]; then manifest row failed "$rslug" "$path" "" "" "git cannot resolve a common dir (raw working-tree tar attempted): $(first_line "$SCR/resolve.err")"; fi
    continue
  fi
  common=$(cd "$common" 2> /dev/null && pwd -P || printf '%s' "$common")
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$path" "$kind" "$branch" "$remote" "$dirty" "$common" >> "$SCR/rowinfo.tsv"
done 3< "$SCR/rows.us"
log "rows=$NROWS resolved=$((NROWS - NVANISHED - NFAILED_RESOLVE)) vanished=$NVANISHED unresolved=$NFAILED_RESOLVE"

# unique common dirs; order: remote-less first, then smallest estimate first (the big remote-backed ones last)
: > "$SCR/commons.raw"
awk -F'\t' '{ nr = ($4 == "NONE") ? 1 : 0; print $6 "\t" nr }' "$SCR/rowinfo.tsv" \
  | sort -t "$(printf '\t')" -k1,1 -k2,2nr \
  | awk -F'\t' '!seen[$1]++ { print $1 "\t" $2 }' > "$SCR/commons.raw"
: > "$SCR/commons.plan"   # noremote est common
TOTAL_BUNDLE_EST=0
while IFS=$'\t' read -r -u 3 common nr; do
  est=$(est_bytes "$common")
  TOTAL_BUNDLE_EST=$((TOTAL_BUNDLE_EST + est))
  printf '%s\t%s\t%s\n' "$nr" "$est" "$common" >> "$SCR/commons.plan"
done 3< "$SCR/commons.raw"
sort -t "$(printf '\t')" -k1,1nr -k2,2n "$SCR/commons.plan" > "$SCR/commons.sorted"
NUNIQUE=$(wc -l < "$SCR/commons.sorted" | tr -d ' ')
log "unique common dirs=$NUNIQUE estimated bundle bytes=$TOTAL_BUNDLE_EST"

# ---------------------------------------------------------------------------------------------
# phase A helpers: dirty snapshots (tracked patch + untracked tar)
# ---------------------------------------------------------------------------------------------
DIFF_FLAGS=(diff --binary --no-ext-diff --no-textconv --default-prefix --no-relative)

dirty_estimate() { # path slug
  local path=$1 slug=$2 patch_bytes keep stats
  patch_bytes=$(G -C "$path" "${DIFF_FLAGS[@]}" HEAD 2> /dev/null | wc -c | tr -d ' ')
  G -C "$path" ls-files -o --exclude-standard -z > "$SCR/$slug.untracked.all" 2> "$SCR/$slug.err" || true
  keep="$SCR/$slug.untracked.keep"
  stats=$(python3 -I "$HELPER" filter-untracked "$path" "$SCR/$slug.untracked.all" "$keep" "$SKIPPED" "$CREDLIST" "$slug" "$MAX_FILE_BYTES")
  # stats: keep_count keep_bytes big nested special cred cred_bytes gone
  printf 'DIRTY  patch~%s untracked(count bytes big nested special cred credbytes gone)=[%s] %s\n' "$patch_bytes" "$stats" "$path"
  echo "$patch_bytes $stats" >> "$SCR/dirty.estimates"
}

dirty_snapshot() { # path slug common
  local path=$1 slug=$2 common=$3 err names credf ncred out rc note excl f unborn=0
  err="$SCR/$slug.err"
  # An unborn HEAD (no commits yet) has nothing to diff against: everything staged lives only in the index and the
  # object database. Capture the staged paths as a tar and the git dir (index + objects) as a raw copy.
  if ! G -C "$path" rev-parse -q --verify HEAD > /dev/null 2>&1; then unborn=1; fi
  # ---- tracked changes
  out="dirty/$slug.tracked.patch"
  names="$SCR/$slug.tracked.names"
  credf="$SCR/$slug.tracked.cred"
  if past_deadline; then
    manifest tracked-patch skipped "$slug" "$path" "" "" "soft deadline reached before this item"
  elif [ "$unborn" -eq 1 ]; then
    manifest tracked-patch empty "$slug" "$path" "" 0 "unborn HEAD (no commits): nothing to diff against; staged paths are in the staged-tar, the index and objects in the gitdir-tar"
    if G -C "$path" ls-files --cached -z > "$SCR/$slug.staged.all" 2> "$err"; then
      tar_list staged-tar "$path" "$slug" "$SCR/$slug.staged.all" "dirty/$slug.staged.tar" "no staged entries"
    else
      manifest staged-tar failed "$slug" "$path" "" "" "ls-files --cached failed: $(first_line "$err")"
    fi
    gitdir_tar "$common" "unborn HEAD: staged blobs exist only in the object database"
  elif ! G -C "$path" diff --name-only -z --no-ext-diff --no-relative HEAD > "$names" 2> "$err"; then
    manifest tracked-patch failed "$slug" "$path" "" "" "diff --name-only HEAD failed: $(first_line "$err")"
  else
    ncred=$(python3 -I "$HELPER" cred-names "$path" "$names" "$credf" tracked-patch "$slug" "$CREDLIST")
    excl=()
    if [ "${ncred:-0}" -gt 0 ]; then
      while IFS= read -r -d '' f <&4; do excl+=(":(top,exclude,literal)$f"); done 4< "$credf"
    fi
    if [ "${#excl[@]}" -gt 0 ]; then
      G -C "$path" "${DIFF_FLAGS[@]}" HEAD -- ':(top)' "${excl[@]}" > "$RUN/$out" 2> "$err"
    else
      G -C "$path" "${DIFF_FLAGS[@]}" HEAD > "$RUN/$out" 2> "$err"
    fi
    rc=$?
    note=""
    [ "${ncred:-0}" -gt 0 ] && note="excluded $ncred credential-pattern path(s), listed in credential-skipped.txt"
    if [ "$rc" -ne 0 ]; then
      manifest tracked-patch failed "$slug" "$path" "$out" "" "git diff exit $rc: $(first_line "$err") $note"
    elif [ ! -s "$RUN/$out" ]; then
      manifest tracked-patch empty "$slug" "$path" "$out" 0 "no tracked changes vs HEAD $note"
    else
      manifest tracked-patch ok "$slug" "$path" "$out" "$(grep -c '^diff --git' "$RUN/$out")" "$note"
    fi
  fi
  # ---- untracked, non-ignored files
  if past_deadline; then
    manifest untracked-tar skipped "$slug" "$path" "" "" "soft deadline reached before this item"
    return
  fi
  if ! G -C "$path" ls-files -o --exclude-standard -z > "$SCR/$slug.untracked.all" 2> "$err"; then
    manifest untracked-tar failed "$slug" "$path" "" "" "ls-files -o failed: $(first_line "$err")"
    return
  fi
  tar_list untracked-tar "$path" "$slug" "$SCR/$slug.untracked.all" "dirty/$slug.untracked.tar" "no untracked files to archive"
}

# tar_list <kind> <path> <slug> <NUL-separated file list> <out rel> <empty-note>
# Filters the list (credential patterns, >2 GiB files, nested-repo entries), then tars the rest relative to <path>.
tar_list() {
  local kind=$1 path=$2 slug=$3 all=$4 out=$5 emptynote=$6 keep stats entries payload big nested special cred credb gone note rc terr
  keep="$SCR/$slug.$kind.keep"
  terr="$SCR/$slug.$kind.tar.err"
  stats=$(python3 -I "$HELPER" filter-untracked "$path" "$all" "$keep" "$SKIPPED" "$CREDLIST" "$slug" "$MAX_FILE_BYTES")
  # stats: keep_count keep_bytes big nested special cred cred_bytes gone
  if ! read -r entries payload big nested special cred credb gone <<< "$stats"; then
    manifest "$kind" failed "$slug" "$path" "" "" "file-list filter produced no stats"
    return
  fi
  note="payload_bytes=$payload skipped:big=$big,nested=$nested,special=$special,vanished=$gone credential=$cred"
  if [ "$entries" -eq 0 ]; then
    manifest "$kind" empty "$slug" "$path" "" 0 "$emptynote; $note"
    return
  fi
  tar -n -C "$path" --null -T "$keep" -cf "$RUN/$out" 2> "$terr"
  rc=$?
  if [ -s "$terr" ]; then
    cp "$terr" "$RUN/$out.err"
    manifest tar-log ok "$slug" "$path" "$out.err" "" "tar stderr for $kind $slug"
  fi
  if [ "$rc" -ne 0 ]; then
    manifest "$kind" failed "$slug" "$path" "$out" "$entries" "tar exit $rc: $(first_line "$terr") $note"
  else
    manifest "$kind" ok "$slug" "$path" "$out" "$entries" "$note"
  fi
}

# Rows whose directory exists but whose gitfile no longer resolves (worktree admin entry pruned or parent repo
# moved): git cannot snapshot them, so the working tree itself is tarred (deviation from the original spec).
orphan_snapshot() { # path slug
  local path=$1 slug=$2 err list
  err="$SCR/$slug.orphan.err"
  list="$SCR/$slug.orphan.all"
  if past_deadline; then
    manifest orphan-tree-tar skipped "$slug" "$path" "" "" "soft deadline reached before this item"
    return
  fi
  (cd "$path" && find . -xdev \( -type f -o -type l \) -print0) > "$list" 2> "$err"
  if [ ! -s "$list" ]; then
    manifest orphan-tree-tar failed "$slug" "$path" "" "" "no files listed: $(first_line "$err")"
    return
  fi
  tar_list orphan-tree-tar "$path" "$slug" "$list" "dirty/$slug.orphan-tree.tar" "no files in orphan working tree"
}

# ---------------------------------------------------------------------------------------------
# phase S: stash entries below refs/stash (a bundle --all only carries the top one)
# ---------------------------------------------------------------------------------------------
stash_extras() { # common
  local common=$1 cslug n i sha empty err out rc
  cslug=$(slugify "$common")
  err="$SCR/$cslug.stash.err"
  G --git-dir="$common" log -g --format=%H refs/stash > "$SCR/$cslug.stash.list" 2> /dev/null || : > "$SCR/$cslug.stash.list"
  n=$(wc -l < "$SCR/$cslug.stash.list" | tr -d ' ')
  [ "${n:-0}" -gt 1 ] || return 0
  if [ "$MODE" = dry ]; then
    printf 'STASH  extra-entries=%s %s\n' "$((n - 1))" "$common"
    return 0
  fi
  if past_deadline; then
    manifest stash-patch skipped "$cslug" "$common" "" "" "soft deadline reached before this item"
    return 0
  fi
  out="dirty/$cslug.stash-reflog.txt"
  G --git-dir="$common" log -g --format='%gd%x09%H%x09%gs' refs/stash > "$RUN/$out" 2> "$err"
  rc=$?
  manifest stash-reflog "$([ "$rc" -eq 0 ] && echo ok || echo failed)" "$cslug" "$common" "$out" "$n" "refs/stash reflog, $n entries"
  empty=$(G --git-dir="$common" hash-object -t tree /dev/null 2> /dev/null)
  i=1
  while [ "$i" -lt "$n" ]; do
    sha=$(sed -n "$((i + 1))p" "$SCR/$cslug.stash.list")
    out="dirty/$cslug.stash$i.patch"
    (
      G --git-dir="$common" "${DIFF_FLAGS[@]}" "$sha^1" "$sha" 2> "$err" || exit 1
      if G --git-dir="$common" rev-parse -q --verify "$sha^3" > /dev/null 2>&1; then
        G --git-dir="$common" "${DIFF_FLAGS[@]}" "$empty" "$sha^3" 2>> "$err" || exit 1
      fi
    ) > "$RUN/$out"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      manifest stash-patch failed "$cslug" "$common" "$out" "" "stash@{$i} $sha: $(first_line "$err")"
    else
      manifest stash-patch ok "$cslug" "$common" "$out" 1 "stash@{$i} $sha tracked diff vs its base, plus untracked part if present"
    fi
    i=$((i + 1))
  done
}

# ---------------------------------------------------------------------------------------------
# phase B/C helpers: bundles
# ---------------------------------------------------------------------------------------------
is_partial_clone() { # common: promisor remote / extensions.partialclone => blobs may live only on the remote
  if G --git-dir="$1" config --get-regexp '^remote\..*\.promisor$' 2> /dev/null | grep -q true; then return 0; fi
  G --git-dir="$1" config --get extensions.partialclone > /dev/null 2>&1
}

# gitdir_tar <common> <why>: raw tar of the git common dir itself (objects, index, refs, config) when a bundle cannot
# capture the repo (partial clone, unborn HEAD with staged blobs, or a failed bundle). Aborted-download tmp_pack_* junk is
# left out; a config carrying a user:password@ URL is left out and listed by path and size only.
gitdir_tar() {
  local common=$1 why=$2 slug rel parent base terr rc entries cfgsize
  local -a excl
  slug=$(slugify "$common")
  rel="bundles/$slug.gitdir.tar"
  if [ -e "$SCR/gitdir-tar.$slug" ]; then return 0; fi
  : > "$SCR/gitdir-tar.$slug"
  if past_deadline; then
    manifest gitdir-tar skipped "$slug" "$common" "" "" "soft deadline reached before this item"
    return
  fi
  parent=$(dirname "$common")
  base=$(basename "$common")
  terr="$SCR/$slug.gitdir.tar.err"
  excl=(--exclude 'tmp_pack_*')
  if grep -Eq '://[^/ @]+:[^/ @]+@' "$common/config" 2> /dev/null; then
    excl+=(--exclude "$base/config")
    cfgsize=$(stat -f %z "$common/config" 2> /dev/null || echo 0)
    printf 'gitdir-tar\t%s\t%s/config\t%s\n' "$slug" "$base" "$cfgsize" >> "$CREDLIST"
  fi
  tar -C "$parent" "${excl[@]}" -cf "$RUN/$rel" "$base" 2> "$terr"
  rc=$?
  entries=$(tar -tf "$RUN/$rel" 2> /dev/null | wc -l | tr -d ' ')
  if [ -s "$terr" ]; then
    cp "$terr" "$RUN/$rel.err"
    manifest tar-log ok "$slug" "$common" "$rel.err" "" "tar stderr for gitdir-tar $slug"
  fi
  if [ "$rc" -ne 0 ]; then
    manifest gitdir-tar failed "$slug" "$common" "$rel" "$entries" "tar exit $rc: $(first_line "$terr") ($why)"
  else
    manifest gitdir-tar ok "$slug" "$common" "$rel" "$entries" "raw copy of the git dir: $why"
  fi
}

full_bundle() { # common est
  local common=$1 est=$2 slug rel err rc nrefs vout
  slug=$(slugify "$common")
  rel="bundles/$slug.bundle"
  err="$SCR/$slug.bundle.err"
  if past_deadline; then
    manifest bundle skipped "$slug" "$common" "" "" "soft deadline reached before this item (est $est bytes)"
    return
  fi
  if is_partial_clone "$common"; then
    gitdir_tar "$common" "partial clone (promisor remote): a bundle needs blobs that only the remote holds, and the network is never used here"
    return
  fi
  G --git-dir="$common" -c pack.threads=2 bundle create -q "$RUN/$rel" --all > /dev/null 2> "$err"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if grep -q 'empty bundle' "$err"; then
      manifest bundle empty "$slug" "$common" "" 0 "no refs to bundle (git refused to create an empty bundle)"
    else
      manifest bundle failed "$slug" "$common" "$([ -f "$RUN/$rel" ] && echo "$rel")" "" "git bundle create exit $rc: $(first_line "$err")"
      gitdir_tar "$common" "bundle create failed ($(first_line "$err")); raw copy instead"
    fi
    return
  fi
  nrefs=$(G --git-dir="$common" bundle list-heads "$RUN/$rel" 2> /dev/null | wc -l | tr -d ' ')
  if vout=$(G --git-dir="$common" bundle verify "$RUN/$rel" 2>&1); then
    manifest bundle ok "$slug" "$common" "$rel" "$nrefs" "verify=ok (est $est bytes)"
  else
    manifest bundle failed "$slug" "$common" "$rel" "$nrefs" "verify FAILED: $(printf '%s' "$vout" | tail -n 1)"
  fi
}

head_bundle() { # path slug
  local path=$1 slug=$2 rel err rc vout
  rel="bundles/$slug.head.bundle"
  err="$SCR/$slug.head.err"
  if past_deadline; then
    manifest head-bundle skipped "$slug" "$path" "" "" "soft deadline reached before this item"
    return
  fi
  G -C "$path" -c pack.threads=2 bundle create -q "$RUN/$rel" HEAD --not --remotes > /dev/null 2> "$err"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if grep -q 'empty bundle' "$err"; then
      manifest head-bundle empty "$slug" "$path" "" 0 "HEAD is fully reachable from a remote-tracking ref (held by the full bundle)"
    else
      manifest head-bundle failed "$slug" "$path" "$([ -f "$RUN/$rel" ] && echo "$rel")" "" "git bundle create HEAD exit $rc: $(first_line "$err")"
    fi
    return
  fi
  if vout=$(G -C "$path" bundle verify "$RUN/$rel" 2>&1); then
    manifest head-bundle ok "$slug" "$path" "$rel" 1 "verify=ok"
  else
    manifest head-bundle failed "$slug" "$path" "$rel" 1 "verify FAILED: $(printf '%s' "$vout" | tail -n 1)"
  fi
}

# ---------------------------------------------------------------------------------------------
# DRY: report the plan with byte estimates, touch nothing
# ---------------------------------------------------------------------------------------------
if [ "$MODE" = dry ]; then
  : > "$SCR/dirty.estimates"
  echo "== bundles (noremote est_bytes common) =="
  while IFS=$'\t' read -r -u 3 nr est common; do
    printf 'BUNDLE noremote=%s est=%s %s\n' "$nr" "$est" "$common"
  done 3< "$SCR/commons.sorted"
  echo "== dirty snapshots =="
  while IFS=$'\t' read -r -u 3 path kind branch remote dirty common; do
    [ "$dirty" -gt 0 ] || continue
    dirty_estimate "$path" "$(slugify "$path")"
    if ! G -C "$path" rev-parse -q --verify HEAD > /dev/null 2>&1; then
      printf 'UNBORN staged_entries=%s (staged-tar + gitdir-tar would be made) %s\n' "$(G -C "$path" ls-files --cached | wc -l | tr -d ' ')" "$path"
    fi
  done 3< "$SCR/rowinfo.tsv"
  echo "== orphan worktrees (raw working-tree tar) =="
  : > "$SCR/orphan.estimates"
  while IFS=$'\t' read -r -u 3 path oslug; do
    (cd "$path" && find . -xdev \( -type f -o -type l \) -print0) > "$SCR/$oslug.orphan.all" 2> /dev/null
    ostats=$(python3 -I "$HELPER" filter-untracked "$path" "$SCR/$oslug.orphan.all" "$SCR/$oslug.orphan.keep" "$SKIPPED" "$CREDLIST" "$oslug" "$MAX_FILE_BYTES")
    printf 'ORPHAN tree(count bytes big nested special cred credbytes gone)=[%s] %s\n' "$ostats" "$path"
    echo "$ostats" >> "$SCR/orphan.estimates"
  done 3< "$SCR/orphans.tsv"
  echo "== detached head bundles =="
  while IFS=$'\t' read -r -u 3 path kind branch remote dirty common; do
    [ "$branch" = "(detached)" ] && printf 'HEAD   %s\n' "$path"
  done 3< "$SCR/rowinfo.tsv"
  echo "== extra stash entries =="
  while IFS=$'\t' read -r -u 3 nr est common; do stash_extras "$common"; done 3< "$SCR/commons.sorted"
  NDIRTY=$(awk -F'\t' '$5>0' "$SCR/rowinfo.tsv" | wc -l | tr -d ' ')
  NHEAD=$(awk -F'\t' '$3=="(detached)"' "$SCR/rowinfo.tsv" | wc -l | tr -d ' ')
  awk -v rows="$NROWS" -v van="$NVANISHED" -v unres="$NFAILED_RESOLVE" -v uniq="$NUNIQUE" -v best="$TOTAL_BUNDLE_EST" -v nd="$NDIRTY" -v nh="$NHEAD" '
    { patch += $1; keepn += $2; keepb += $3; big += $4; nested += $5; special += $6; cred += $7; credb += $8; gone += $9 }
    END {
      printf "SUMMARY rows=%d vanished=%d unresolved=%d unique_common_dirs=%d dirty_rows=%d detached_rows=%d\n", rows, van, unres, uniq, nd, nh
      printf "SUMMARY est_bundle_bytes=%d est_patch_bytes=%d untracked_files=%d untracked_bytes=%d\n", best, patch, keepn, keepb
      printf "SUMMARY skipped: over2GiB=%d nested_repo_entries=%d special=%d credential_files=%d (credential_bytes=%d) vanished_files=%d\n", big, nested, special, cred, credb, gone
      printf "SUMMARY est_total_bytes_before_orphans=%d\n", best + patch + keepb
    }' "$SCR/dirty.estimates"
  awk '{ n += $1; b += $2; cred += $6; credb += $7 } END { printf "SUMMARY orphan_trees files=%d bytes=%d credential_files=%d credential_bytes=%d\n", n, b, cred, credb }' "$SCR/orphan.estimates"
  log "dry run complete; nothing was written outside $SCR"
  exit 0
fi

# ---------------------------------------------------------------------------------------------
# APPLY
# ---------------------------------------------------------------------------------------------
log "== phase A: dirty snapshots (local-only work first) =="
while IFS=$'\t' read -r -u 3 path kind branch remote dirty common; do
  [ "$dirty" -gt 0 ] || continue
  log "dirty snapshot: $path"
  dirty_snapshot "$path" "$(slugify "$path")" "$common"
done 3< "$SCR/rowinfo.tsv"

log "== phase A2: orphan worktrees (raw working-tree tar) =="
while IFS=$'\t' read -r -u 3 path oslug; do
  log "orphan worktree: $path"
  orphan_snapshot "$path" "$oslug"
done 3< "$SCR/orphans.tsv"

log "== phase S: extra stash entries =="
while IFS=$'\t' read -r -u 3 nr est common; do stash_extras "$common"; done 3< "$SCR/commons.sorted"

log "== phase B: head bundles for detached rows =="
while IFS=$'\t' read -r -u 3 path kind branch remote dirty common; do
  [ "$branch" = "(detached)" ] || continue
  log "head bundle: $path"
  head_bundle "$path" "$(slugify "$path")"
done 3< "$SCR/rowinfo.tsv"

log "== phase C: full bundles (remote-less first, smallest first) =="
while IFS=$'\t' read -r -u 3 nr est common; do
  log "bundle: $common (est $est bytes, noremote=$nr)"
  full_bundle "$common" "$est"
done 3< "$SCR/commons.sorted"

manifest skipped-list ok skipped.txt "$RUN/dirty" dirty/skipped.txt "$(wc -l < "$RUN/dirty/skipped.txt" | tr -d ' ')" "files left out of untracked tars (not credential patterns)"
manifest credential-list ok credential-skipped.txt "$RUN/dirty" dirty/credential-skipped.txt "$(wc -l < "$RUN/dirty/credential-skipped.txt" | tr -d ' ')" "credential-pattern files left out: path and size only, contents never read"

log "== summary =="
awk -F'\t' 'NR>1 { c[$1" "$2]++; b[$1" "$2]+=$6; total+=$6 } END { for (k in c) printf "COUNT %-28s n=%d bytes=%d\n", k, c[k], b[k]; printf "TOTAL_BYTES %d\n", total }' "$MANIFEST" | sort
log "rows=$NROWS vanished=$NVANISHED unresolved=$NFAILED_RESOLVE unique_common_dirs=$NUNIQUE"
log "run directory: $RUN"
log "apply complete"
exit 0
