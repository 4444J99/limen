#!/bin/bash
# End-to-end self-test of nongit-homing.sh on a throwaway fixture. Touches nothing outside its own temp directory.
#
# WHY: nongit-homing.sh copies the only existing copy of a directory to an external volume and then lets the operator
# erase the original. It must be proven on a fixture first: that a verified copy really verifies, that every refusal
# path refuses before writing anything, that credentials are listed and never copied, that a database held open in WAL
# mode is captured with its WAL content, and that a source that changes mid-copy is reported as DRIFT and left out of
# the manifest. A checker that has never been seen to fail proves nothing, so a negative control corrupts one
# destination byte and expects `shasum -a 256 -c` to fail.
#
# Isolation: HOME, TMPDIR, the scratch base and the destination root all live under one fresh directory, so a path bug
# in the tool lands on fixture data, never on the operator's. The directory is removed on success and kept on failure.
# shellcheck disable=SC2015 # `test && ok || bad` is safe here: ok and bad always return 0
# shellcheck disable=SC2016 # items files are written with a literal $HOME, which the tool (not this shell) expands
# shellcheck disable=SC2329 # cleanup is invoked by the EXIT trap
set -u
here=$(cd -P "$(dirname "$0")" && pwd -P)
base=$(mktemp -d "${TMPDIR:-/tmp}/nongit-homing-selftest.XXXXXX") || exit 70
base=$(cd -P "$base" && pwd -P) # macOS $TMPDIR is under /var, a symlink to /private/var
export HOME="$base/home" TMPDIR="$base/tmp" HOMING_SCRATCH_BASE="$base/scratch"
unset HOME_NONGIT_CONFIRM HOMING_RUN_NAME HOMING_DEADLINE_SEC HOMING_FREE_RATIO_PCT HOMING_QUIET_PROCESSES \
  HOMING_EXTRA_CRED_FILE_GLOBS HOMING_EXTRA_CRED_DIR_GLOBS NONGIT_HOMING_SQLITE
mkdir -p "$HOME" "$TMPDIR" "$HOMING_SCRATCH_BASE" "$base/ext" "$base/work"
tool="$here/nongit-homing.sh"
ext="$base/ext"
SQLITE=/usr/bin/sqlite3
[ -x "$SQLITE" ] || SQLITE=$(command -v sqlite3) || { echo "sqlite3 is required" >&2; exit 69; }
CONFIRM=conductor-has-decided

fail=0
passes=0
ok() {
  printf 'ok    %s\n' "$*"
  passes=$((passes + 1))
}
bad() {
  printf 'FAIL  %s\n' "$*"
  fail=1
}
OUT=""
RC=0
expect_rc() { # description, expected rc
  if [ "$RC" = "$2" ]; then ok "$1 (rc $RC)"; else bad "$1: expected rc $2, got $RC: $(printf '%s\n' "$OUT" | tail -n 4)"; fi
}
expect_out() { # description, substring of $OUT
  case "$OUT" in *"$2"*) ok "$1" ;; *) bad "$1: output lacks '$2': $(printf '%s\n' "$OUT" | tail -n 4)" ;; esac
}
expect() { # description, command...: ok when the command exits 0
  local d=$1
  shift
  if "$@" > "$base/work/expect.out" 2>&1; then ok "$d"; else bad "$d: $(head -c 300 "$base/work/expect.out")"; fi
}
ext_empty() { [ -z "$(ls -A "$ext")" ]; }
fsize() { wc -c < "$1" | tr -d ' '; }
rows() { "$SQLITE" -readonly "$1" 'select count(*) from t;'; }
integrity() { [ "$("$SQLITE" -readonly "$1" 'PRAGMA integrity_check;')" = ok ]; }
excluded_has() { # run_dir kind path size
  awk -F'\t' -v k="$2" -v p="$3" -v s="$4" '$1==k && $2==p && $3==s {n++} END {exit n ? 0 : 1}' "$1/EXCLUDED.tsv"
}
tree_digest() { # dir: size, mtime and content hash of every regular file except the live database
  (
    cd "$1" || exit 1
    find . -type f ! -name 'live.db*' -exec stat -f '%N %z %m' {} + | sort
    find . -type f ! -name 'live.db*' -exec shasum -a 256 {} + | sort
  )
}
dir_digest() { # dir: every entry's name, size and mtime plus every file's hash (detects any change to a run dir)
  (
    cd "$1" || exit 1
    find . -exec stat -f '%N %z %m' {} + | sort
    find . -type f -exec shasum -a 256 {} + | sort
  )
}

HOLDER_PID=""
APPENDER_PID=""
BUSY_PID=""
stop_pid() { if [ -n "$1" ] && kill -0 "$1" 2> /dev/null; then kill "$1"; fi; }
cleanup() {
  exec 9>&-
  stop_pid "$APPENDER_PID"
  stop_pid "$HOLDER_PID"
  stop_pid "$BUSY_PID"
}
trap cleanup EXIT

# ---- fixture ---------------------------------------------------------------------------------------------------------
docs="$HOME/FixtureDocs"
single="$HOME/FixtureSingle"
mkdir -p "$docs/notes/deep/deeper" "$docs/media" "$docs/cache" "$docs/.ssh" "$docs/data" "$single"
printf 'fixture readme\n' > "$docs/readme.txt"
printf 'non-ascii and a space in the name\n' > "$docs/notes/ünï café.md"
ln -s ../../../readme.txt "$docs/notes/deep/deeper/link-to-readme" # nested relative symlink
ln -s missing-target "$docs/notes/dangling"                         # dangling symlink: recreated, never followed
python3 -I -c 'import os, sys; open(sys.argv[1], "wb").write(os.urandom(int(sys.argv[2])))' "$docs/media/aa-big.bin" 9500000
printf 'small\n' > "$docs/media/zz-small.txt"
printf 'junk\n' > "$docs/cache/junk.tmp"
printf 'FIXTURE_FAKE_SECRET_not_real\n' > "$docs/.env"
printf 'FIXTURE_FAKE_KEY_not_real\n' > "$docs/.ssh/id_ed25519"
printf 'FIXTURE_FAKE_TOKEN_not_real\n' > "$docs/api.token"
mkfifo "$docs/pipe"
(cd "$docs" && python3 -I -c 'import socket; s = socket.socket(socket.AF_UNIX); s.bind("sock"); s.close()')
fill_t() { # db rows: a rollback-journal database named however the caller likes
  "$SQLITE" "$1" "CREATE TABLE t(x INTEGER, y TEXT); WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<$2) INSERT INTO t SELECT x, 'row'||x FROM c;"
}
fill_t "$docs/data/store.dat" 200 # a database with no database-looking name: found by its header
fill_t "$single/one.sqlite" 50
printf 'sibling that the single-file item must not take\n' > "$single/other.txt"

# live.db: WAL mode, held open by a running sqlite3 for the whole test, with every row still only in the -wal.
mkfifo "$base/work/hold.fifo"
"$SQLITE" "$docs/data/live.db" < "$base/work/hold.fifo" > "$base/work/holder.out" 2> "$base/work/holder.err" &
HOLDER_PID=$!
exec 9> "$base/work/hold.fifo"
printf '%s\n' 'PRAGMA journal_mode=WAL;' 'PRAGMA wal_autocheckpoint=0;' 'CREATE TABLE t(x INTEGER, y TEXT);' \
  "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<600) INSERT INTO t SELECT x, 'row'||x FROM c;" >&9
held=no
for _ in $(seq 1 100); do
  if [ -s "$docs/data/live.db-wal" ] && [ "$(rows "$docs/data/live.db" 2> /dev/null)" = 600 ]; then
    held=yes
    break
  fi
  sleep 0.1
done
if [ "$held" = yes ]; then ok "fixture: live.db is held open in WAL mode with 600 rows (-wal is non-empty)"; else bad "fixture: the WAL holder never came up: $(cat "$base/work/holder.err")"; fi
cp "$docs/data/live.db" "$base/work/naive.db"
[ "$(rows "$base/work/naive.db" 2> /dev/null)" = 600 ] && bad "fixture: a naive copy of the main file already has the WAL rows (the test would prove nothing)" || ok "fixture: a naive file copy of live.db loses the WAL rows, so the snapshot has to do real work"

# shellcheck disable=SC2016 # $HOME is expanded by the tool, not by this shell
{
  printf '%s\t%s\t%s\t%s\n' fixture-docs '$HOME/FixtureDocs' home/FixtureDocs cache
  printf '%s\t%s\t%s\n' fixture-single '$HOME/FixtureSingle/one.sqlite' home/FixtureSingle/one.sqlite
} > "$base/items.tsv"
tree_digest "$docs" > "$base/work/tree.before"
shasum -a 256 "$docs/data/live.db" > "$base/work/livedb.before"

# ---- refusals: every one must happen before anything is written -------------------------------------------------------
OUT=$(bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "apply without the confirmation variable is refused" 2
expect_out "the refusal says why" "REFUSED"
ext_empty && ok "  ...and nothing was created" || bad "  ...but something was created in the destination"
OUT=$(HOME_NONGIT_CONFIRM=yes bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "apply with a wrong confirmation value is refused" 2
OUT=$(HOME_NONGIT_CONFIRM=$CONFIRM HOMING_FREE_RATIO_PCT=1000000000 bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "apply refuses when free space is insufficient" 28
expect_out "  ...naming the shortfall" "NOT ENOUGH FREE SPACE"
ext_empty && ok "  ...and nothing was created" || bad "  ...but something was created in the destination"
ln -s /bin/sleep "$base/work/nongit-selftest-busy" # a symlink gives the process a name of our own (a copy would be killed: signature)
"$base/work/nongit-selftest-busy" 300 &
BUSY_PID=$!
disown "$BUSY_PID" # no "Terminated" job notice when it is stopped
sleep 0.3
expect "fixture: the stand-in process is visible to pgrep -x" pgrep -x nongit-selftest-busy
OUT=$(HOME_NONGIT_CONFIRM=$CONFIRM HOMING_QUIET_PROCESSES="nongit-selftest-absent nongit-selftest-busy" bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "apply refuses while a listed quiet-process is running" 75
expect_out "  ...naming it" "nongit-selftest-busy is running"
stop_pid "$BUSY_PID"
BUSY_PID=""
ext_empty && ok "  ...and nothing was created" || bad "  ...but something was created in the destination"
OUT=$(bash "$tool" dry "$base/items.tsv" "$base/not-mounted" 2>&1)
RC=$?
expect_rc "a destination root that does not exist is an error, never created" 66
[ ! -e "$base/not-mounted" ] && ok "  ...and it was not created" || bad "  ...but it was created"
OUT=$(bash "$tool" dry "$base/items.tsv" "relative/dest" 2>&1)
RC=$?
expect_rc "a relative destination root is refused" 64
printf 'a\t$HOME/FixtureDocs\thome/a\nb\t$HOME/FixtureDocs/notes\thome/b\n' > "$base/overlap.tsv"
OUT=$(bash "$tool" dry "$base/overlap.tsv" "$ext" 2>&1)
RC=$?
expect_rc "overlapping items are refused" 64
expect_out "  ...naming the carve-out that would fix it" "add '=notes'"
printf 'a\t$HOME/FixtureDocs\t../escape\n' > "$base/escape.tsv"
OUT=$(bash "$tool" dry "$base/escape.tsv" "$ext" 2>&1)
RC=$?
expect_rc "a destination path that climbs out of the run directory is refused" 64
printf 'a\t$HOME/NoSuchDir\thome/a\n' > "$base/missing.tsv"
OUT=$(bash "$tool" dry "$base/missing.tsv" "$ext" 2>&1)
RC=$?
expect_rc "a dry plan with a missing source fails instead of passing" 1
expect_out "  ...and says so" "ERROR_SOURCE_MISSING"
ext_empty && ok "all refusals left the destination empty" || bad "a refusal wrote into the destination"

# ---- dry run ---------------------------------------------------------------------------------------------------------
OUT=$(bash "$tool" dry "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "dry run succeeds" 0
expect_out "dry run reports itself as a dry run" "RESULT: DRY-RUN (nothing written)"
expect_out "dry run plans the three databases" "snapshots=3"
expect_out "dry run plans the four plain files" "files=4"
ext_empty && ok "dry run wrote nothing to the destination" || bad "dry run wrote into the destination"
ls "$HOMING_SCRATCH_BASE"/nongit-homing-dry-*.log > /dev/null 2>&1 && ok "dry run kept a durable plan log in the scratch base" || bad "no dry plan log in the scratch base"

# ---- the clean apply -------------------------------------------------------------------------------------------------
run="$ext/run-main"
OUT=$(HOME_NONGIT_CONFIRM=$CONFIRM HOMING_RUN_NAME=run-main HOMING_QUIET_PROCESSES=nongit-selftest-absent bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "apply with the confirmation succeeds (a listed quiet-process that is not running does not block it)" 0
expect_out "apply reports PASS" "RESULT: PASS"
for f in MANIFEST.sha256 MANIFEST.tsv EXCLUDED.tsv RESULT.txt RUN.log DRY-PLAN.log; do
  [ -s "$run/$f" ] && ok "run dir has $f" || bad "run dir lacks $f"
done
[ "$(grep -c -e '^RESULT: PASS$' -e '^verified=7$' -e '^errors=0$' -e '^drift=0$' -e '^mismatch=0$' "$run/RESULT.txt")" = 5 ] \
  && ok "RESULT.txt has all five expected lines" || bad "RESULT.txt lacks one of: RESULT: PASS, verified=7, errors=0, drift=0, mismatch=0"
[ "$(wc -l < "$run/MANIFEST.sha256" | tr -d ' ')" = 7 ] && ok "MANIFEST.sha256 has exactly 7 lines (4 plain files + 3 database snapshots)" || bad "MANIFEST.sha256 line count is not 7"
for rel in home/FixtureDocs/readme.txt "home/FixtureDocs/notes/ünï café.md" home/FixtureDocs/media/aa-big.bin home/FixtureDocs/media/zz-small.txt \
  home/FixtureDocs/data/live.db home/FixtureDocs/data/store.dat home/FixtureSingle/one.sqlite; do
  expect "manifest lists $rel" grep -qF "  $rel" "$run/MANIFEST.sha256"
done
OUT=$(cd "$run" && shasum -a 256 -c MANIFEST.sha256 2>&1)
RC=$?
expect_rc "shasum -a 256 -c MANIFEST.sha256 passes on the run directory" 0
[ "$(printf '%s\n' "$OUT" | grep -c ': OK$')" = 7 ] && ok "  ...with 7 files reported OK (a name with a space and non-ASCII letters round-trips)" || bad "  ...but not 7 OK lines: $OUT"

# the databases
for pair in "home/FixtureDocs/data/live.db:600" "home/FixtureDocs/data/store.dat:200" "home/FixtureSingle/one.sqlite:50"; do
  db="$run/${pair%%:*}"
  want=${pair##*:}
  integrity "$db" && ok "integrity_check ok on ${pair%%:*}" || bad "integrity_check failed on ${pair%%:*}"
  got=$(rows "$db" 2>&1)
  [ "$got" = "$want" ] && ok "${pair%%:*} holds all $want rows" || bad "${pair%%:*} has '$got' rows, expected $want"
  { [ ! -e "$db-wal" ] && [ ! -e "$db-shm" ] && [ ! -e "$db-journal" ]; } && ok "  ...with no -wal/-shm/-journal sidecar" || bad "  ...but a sidecar was left beside it"
done
[ ! -e "$run/home/FixtureSingle/other.txt" ] && ok "the single-file item took only its own file" || bad "the single-file item also copied its sibling"

# credentials, special files, item excludes
[ -z "$(find "$run" \( -name .env -o -name .ssh -o -name '*.token' -o -name 'id_*' \) -print)" ] && ok "no credential-looking file or directory was copied" || bad "a credential-looking path exists in the run dir"
excluded_has "$run" credential-file "$docs/.env" "$(fsize "$docs/.env")" && ok "EXCLUDED.tsv lists .env by name and size" || bad "EXCLUDED.tsv lacks .env with its size"
excluded_has "$run" credential-file "$docs/api.token" "$(fsize "$docs/api.token")" && ok "EXCLUDED.tsv lists api.token by name and size" || bad "EXCLUDED.tsv lacks api.token with its size"
excluded_has "$run" credential-dir "$docs/.ssh" "$(fsize "$docs/.ssh/id_ed25519")" && ok "EXCLUDED.tsv lists the .ssh directory by name and size" || bad "EXCLUDED.tsv lacks .ssh with its size"
grep -rqF FIXTURE_FAKE "$ext" && bad "a fake secret's CONTENT appears somewhere under the destination" || ok "no fake secret content appears anywhere under the destination"
excluded_has "$run" special-file "$docs/pipe" 0 && ok "EXCLUDED.tsv lists the FIFO (and the run did not hang on it)" || bad "EXCLUDED.tsv lacks the FIFO"
excluded_has "$run" special-file "$docs/sock" 0 && ok "EXCLUDED.tsv lists the socket" || bad "EXCLUDED.tsv lacks the socket"
{ [ ! -e "$run/home/FixtureDocs/pipe" ] && [ ! -e "$run/home/FixtureDocs/sock" ]; } && ok "neither special file exists in the run dir" || bad "a special file was created in the run dir"
[ ! -e "$run/home/FixtureDocs/cache" ] && ok "the item exclude glob kept cache/ out" || bad "cache/ was copied despite the exclude glob"
excluded_has "$run" item-excluded "$docs/cache" "$(fsize "$docs/cache/junk.tmp")" && ok "  ...and EXCLUDED.tsv lists it" || bad "  ...but EXCLUDED.tsv does not list it"

# symlinks
link="$run/home/FixtureDocs/notes/deep/deeper/link-to-readme"
{ [ -L "$link" ] && [ "$(readlink "$link")" = ../../../readme.txt ]; } && ok "the nested symlink is a symlink with the same target" || bad "the nested symlink is wrong"
{ [ -L "$run/home/FixtureDocs/notes/dangling" ] && [ "$(readlink "$run/home/FixtureDocs/notes/dangling")" = missing-target ]; } && ok "the dangling symlink was recreated, not followed" || bad "the dangling symlink is wrong"
[ "$(cat "$link")" = "fixture readme" ] && ok "  ...and the nested symlink resolves inside the run dir" || bad "  ...but it does not resolve to the copied readme"

# sources untouched
tree_digest "$docs" > "$base/work/tree.after"
cmp -s "$base/work/tree.before" "$base/work/tree.after" && ok "every source file is unchanged (path, size, mtime, content)" || bad "a source file changed"
shasum -a 256 "$docs/data/live.db" > "$base/work/livedb.after"
cmp -s "$base/work/livedb.before" "$base/work/livedb.after" && ok "the live database's main file is unchanged" || bad "the live database's main file changed"

# ---- a second apply into the same run dir ------------------------------------------------------------------------------
dir_digest "$run" > "$base/work/run.before"
OUT=$(HOME_NONGIT_CONFIRM=$CONFIRM HOMING_RUN_NAME=run-main bash "$tool" apply "$base/items.tsv" "$ext" 2>&1)
RC=$?
expect_rc "a second apply into the same run dir is refused" 73
expect_out "  ...saying the run directory already exists" "already exists"
dir_digest "$run" > "$base/work/run.after"
cmp -s "$base/work/run.before" "$base/work/run.after" && ok "  ...and the first run is byte-for-byte untouched" || bad "  ...but the first run's files changed"
[ "$(ls "$ext")" = run-main ] && ok "  ...and no other directory appeared" || bad "  ...but the destination now holds: $(ls "$ext")"

# ---- negative control: the checker must be able to fail ----------------------------------------------------------------
cp -R "$run" "$base/negctl"
python3 -I -c 'import sys; f = open(sys.argv[1], "r+b"); f.seek(1000); b = f.read(1); f.seek(1000); f.write(bytes([b[0] ^ 0xFF]))' \
  "$base/negctl/home/FixtureDocs/media/aa-big.bin"
OUT=$(cd "$base/negctl" && shasum -a 256 -c MANIFEST.sha256 2>&1)
RC=$?
[ "$RC" != 0 ] && ok "NEGATIVE CONTROL: shasum -c fails after one destination byte is flipped (rc $RC)" || bad "NEGATIVE CONTROL: shasum -c still passed on a corrupted copy, so the checker proves nothing"
{ [ "$(printf '%s\n' "$OUT" | grep -c ': FAILED$')" = 1 ] && printf '%s\n' "$OUT" | grep -q 'aa-big.bin: FAILED$'; } && ok "  ...and it names exactly the corrupted file" || bad "  ...but the FAILED lines are wrong: $OUT"
[ "$(printf '%s\n' "$OUT" | grep -c ': OK$')" = 6 ] && ok "  ...while the other 6 still read OK" || bad "  ...but the OK count is not 6"
OUT=$(cd "$run" && shasum -a 256 -c MANIFEST.sha256 2>&1)
RC=$?
expect_rc "the original run dir still verifies after the control" 0

# ---- mid-copy change: DRIFT ------------------------------------------------------------------------------------------
drift="$HOME/FixtureDrift"
mkdir -p "$drift"
python3 -I -c 'import os, sys; open(sys.argv[1], "wb").write(os.urandom(int(sys.argv[2])))' "$drift/aa-big.bin" 100000000
printf 'moving\n' > "$drift/zz-moving.txt"
# shellcheck disable=SC2016
printf '%s\t%s\t%s\n' fixture-drift '$HOME/FixtureDrift' home/FixtureDrift > "$base/drift.tsv"
# aa-big.bin sorts before zz-moving.txt, so it is copied first; the appender touches zz-moving.txt every 5 ms from before
# the tool starts until after it exits, so the file changes between the walk's stat and the post-copy check.
(while :; do
  printf x >> "$drift/zz-moving.txt"
  sleep 0.005
done) &
APPENDER_PID=$!
disown "$APPENDER_PID"
OUT=$(HOME_NONGIT_CONFIRM=$CONFIRM HOMING_RUN_NAME=run-drift bash "$tool" apply "$base/drift.tsv" "$ext" 2>&1)
RC=$?
stop_pid "$APPENDER_PID"
APPENDER_PID=""
expect_rc "a source that changes mid-copy makes the run fail" 1
expect_out "  ...reporting DRIFT" "problem=DRIFT"
expect_out "  ...naming the file that moved" "zz-moving.txt"
grep -q '^RESULT: FAIL$' "$ext/run-drift/RESULT.txt" && ok "  ...and RESULT.txt says FAIL" || bad "  ...but RESULT.txt does not say FAIL"
grep -qF "zz-moving.txt" "$ext/run-drift/MANIFEST.sha256" && bad "  ...but the drifted file is listed in MANIFEST.sha256 as verified" || ok "  ...and the drifted file is NOT in MANIFEST.sha256"
grep -qF "home/FixtureDrift/aa-big.bin" "$ext/run-drift/MANIFEST.sha256" && ok "  ...while the stable file beside it is" || bad "  ...but the stable file is missing from the manifest"
OUT=$(cd "$ext/run-drift" && shasum -a 256 -c MANIFEST.sha256 2>&1)
RC=$?
expect_rc "  ...and what the drift run did list still verifies" 0

# ---- deadline ----------------------------------------------------------------------------------------------------------
printf '#!/bin/sh\nexec sleep 30\n' > "$base/work/hang-sqlite.sh"
chmod 755 "$base/work/hang-sqlite.sh"
# shellcheck disable=SC2016
printf '%s\t%s\t%s\n' fixture-single '$HOME/FixtureSingle/one.sqlite' home/FixtureSingle/one.sqlite > "$base/single.tsv"
before=$(ls "$ext")
started=$(date +%s)
OUT=$(NONGIT_HOMING_SQLITE="$base/work/hang-sqlite.sh" HOMING_DEADLINE_SEC=2 bash "$tool" dry "$base/single.tsv" "$ext" 2>&1)
RC=$?
elapsed=$(($(date +%s) - started))
expect_rc "a hung sqlite3 is cut off by the deadline and the run fails" 1
expect_out "  ...reporting the deadline" "problem=DEADLINE"
[ "$elapsed" -lt 20 ] && ok "  ...within ${elapsed}s (limit 2s plus start-up), not the 30s the stub sleeps" || bad "  ...but only after ${elapsed}s"
[ "$(ls "$ext")" = "$before" ] && ok "  ...and the destination is unchanged" || bad "  ...but the destination changed"

# ---- finish ------------------------------------------------------------------------------------------------------------
exec 9>&-
wait "$HOLDER_PID"
HOLDER_PID=""
if [ "$fail" = 0 ]; then
  rm -rf "$base"
  echo "RESULT: PASS ($passes checks)"
  exit 0
fi
echo "RESULT: FAIL ($passes checks passed; fixture kept for inspection: $base)"
exit 1
