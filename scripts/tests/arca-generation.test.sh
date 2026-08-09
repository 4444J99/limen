#!/usr/bin/env bash
# arca-generation.test.sh — regression test for ARCA generation rotation (scripts/arca.sh, POTESTAS 0.3, #2089).
#
# Why it exists: arca.sh backs up the entire private estate and is beat-wired, but its rotation
# path was never exercised anywhere automated — a rewrite could break `backup`, the rotation,
# or restore with no gate noticing. These fixtures are hermetic: a temp workspace holds the fake
# _*-private stores, a temp vault dir holds the clone, `ARCA_CLONE_URL_BASE=file://` points the
# clone/push at local bare remotes, and PATH-shimmed fake `gh` + `security` satisfy repo-view and
# keychain lookups. Nothing here touches the real Keychain, the real ~/.arca-vault, or any real
# organvm repo — the ciphertext never leaves $work.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
ARCA="$ROOT/scripts/arca.sh"
[ -f "$ARCA" ] || { echo "FAIL: cannot find arca.sh at $ARCA" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Hermetic identity (commit without touching any real gitconfig) + no prompts ever.
export GIT_AUTHOR_NAME="arca-test" GIT_AUTHOR_EMAIL="arca-test@localhost"
export GIT_COMMITTER_NAME="arca-test" GIT_COMMITTER_EMAIL="arca-test@localhost"
export GIT_TERMINAL_PROMPT=0

# ── shims ───────────────────────────────────────────────────────────────────────
mkdir -p "$work/bin" "$work/gh" "$work/keychain" "$work/ws"
export FAKE_GH_BASE="$work/gh" FAKE_KEYCHAIN="$work/keychain"
export FAKE_GH_PUSHEDAT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$work/bin/gh" <<'SH'
#!/usr/bin/env bash
# fake gh: `repo view` / `repo create` against local bare remotes under $FAKE_GH_BASE.
# A repo "owner/name" lives at $FAKE_GH_BASE/owner/name.git; diskUsage is read from a
# per-repo file $FAKE_GH_BASE/disk/owner_name (KB, default 128).
set -u
BASE="$FAKE_GH_BASE"
[ "${1:-}" = repo ] || exit 1
op="${2:-}"; name="${3:-}"
repo_dir="$BASE/$name.git"
if [ "$op" = view ]; then
  if [ ! -d "$repo_dir" ]; then
    echo "gh: GraphQL: Could not resolve to a Repository with the name '$name'. (repository)" >&2
    exit 1
  fi
  shift 3
  field=""
  while [ $# -gt 0 ]; do
    if [ "$1" = "--json" ]; then field="$2"; shift 2
    elif [ "$1" = "-q" ]; then shift 2
    else shift; fi
  done
  case "$field" in
    visibility) echo PRIVATE ;;
    pushedAt) cat "$FAKE_GH_PUSHEDAT" 2>/dev/null || echo "2026-08-08T00:00:00Z" ;;
    diskUsage) cat "$BASE/disk/$(printf '%s' "$name" | tr '/' '_')" 2>/dev/null || echo 128 ;;
  esac
  exit 0
fi
if [ "$op" = create ]; then
  mkdir -p "$(dirname "$repo_dir")"
  if [ ! -d "$repo_dir" ]; then
    git init -q --bare "$repo_dir"
    git --git-dir="$repo_dir" symbolic-ref HEAD refs/heads/main
  fi
  exit 0
fi
exit 1
SH

cat > "$work/bin/security" <<'SH'
#!/usr/bin/env bash
# fake security: find-generic-password / add-generic-password against a flat keydir.
set -u
cmd=""; svc=""; keyval=""
while [ $# -gt 0 ]; do
  case "$1" in
    find-generic-password) cmd=find; shift ;;
    add-generic-password) cmd=add; shift ;;
    -s) svc="$2"; shift 2 ;;
    -a) shift 2 ;;
    -w) if [ "$cmd" = add ]; then keyval="$2"; shift 2; else shift; fi ;;
    *) shift ;;
  esac
done
case "$cmd" in
  find) kf="$FAKE_KEYCHAIN/$svc.key"; [ -f "$kf" ] || exit 1; cat "$kf" ;;
  add) mkdir -p "$FAKE_KEYCHAIN"; printf '%s' "$keyval" > "$FAKE_KEYCHAIN/$svc.key" ;;
esac
SH
chmod +x "$work/bin/gh" "$work/bin/security"
export PATH="$work/bin:$PATH"

# ── harness ─────────────────────────────────────────────────────────────────────
pass=0; fail=0
# run_expect <want-rc> <grep-pattern|-> <label> <cmd...>  — runs cmd, checks rc + output
run_expect() {
  local want_rc="$1" pattern="$2" label="$3"; shift 3
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [ "$rc" != "$want_rc" ]; then
    echo "  MISMATCH ($label): want exit $want_rc got $rc"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  if [ "$pattern" != "-" ] && ! printf '%s\n' "$out" | grep -q "$pattern"; then
    echo "  MISMATCH ($label): output missing /$pattern/"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  pass=$((pass+1))
}
json_get() { # json_get <file> <python-expr>
  python3 - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(eval(sys.argv[2]))  # noqa: S307 — controlled test expression
PY
}

# The fixture estate for the primary workspace/vault.
export ARCA_WORKSPACE="$work/ws" ARCA_VAULT_DIR="$work/vault"
export ARCA_KEY_SERVICE="test-arca-vault" ARCA_CLONE_URL_BASE="file://$work/gh"

# ── Case 1: no verb is a loud exit 2 with usage on stderr (never a silent backup) ──
out="$("$ARCA" 2>&1)"; rc=$?
if [ "$rc" = "2" ] && printf '%s\n' "$out" | grep -q "A VERB IS REQUIRED"; then
  pass=$((pass+1))
else
  echo "  MISMATCH (case1 bare invocation): rc=$rc"; printf '%s\n' "$out" | sed 's/^/    /'; fail=$((fail+1))
fi

# ── Case 2: help exits 0 ──
run_expect 0 "A VERB IS REQUIRED" "case2 help" "$ARCA" help

# ── Case 3: unknown verb dies with FATAL ──
run_expect 1 "unknown verb" "case3 unknown verb" "$ARCA" frobnicate

# ── Case 4: seed backup seals + pushes to a depth-1 private clone, gen 1 ──
mkdir -p "$work/ws/_finance-private"
printf 'the docket\n' > "$work/ws/_finance-private/ledger.txt"
run_expect 0 "sealed _finance-private" "case4 seed backup" "$ARCA" backup
[ -d "$work/vault/.git" ] || { echo "  MISMATCH (case4 vault clone absent)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_generation']['current']")" = "1" ] \
  || { echo "  MISMATCH (case4 gen current)" ; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_generation']['repo']")" = "organvm/arca" ] \
  || { echo "  MISMATCH (case4 gen repo)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_finance-private']['gen']")" = "1" ] \
  || { echo "  MISMATCH (case4 store gen)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "len(d['_generations'])")" = "0" ] \
  || { echo "  MISMATCH (case4 no archived gens yet)"; fail=$((fail+1)); }
git --git-dir="$work/gh/organvm/arca.git" rev-parse main >/dev/null 2>&1 \
  || { echo "  MISMATCH (case4 remote never got the push)"; fail=$((fail+1)); }

# ── Case 5: an unchanged re-run makes NO commit and no push ──
before_remote="$(git --git-dir="$work/gh/organvm/arca.git" rev-parse main)"
run_expect 0 "nothing to seal" "case5 no-op re-run" "$ARCA" backup
after_remote="$(git --git-dir="$work/gh/organvm/arca.git" rev-parse main)"
[ "$before_remote" = "$after_remote" ] || { echo "  MISMATCH (case5 no-op made a commit)"; fail=$((fail+1)); }

# ── Case 6: a changed store re-seals and advances the remote ──
printf 'added later\n' >> "$work/ws/_finance-private/ledger.txt"
run_expect 0 "sealed _finance-private" "case6 changed store" "$ARCA" backup
[ "$(git --git-dir="$work/gh/organvm/arca.git" rev-parse main)" != "$after_remote" ] \
  || { echo "  MISMATCH (case6 change produced no remote advance)"; fail=$((fail+1)); }

# ── Case 7: chunking — an oversized store ships as parts and restores byte-identical ──
mkdir -p "$work/ws/_memories-private"
dd if=/dev/urandom of="$work/ws/_memories-private/seed.bin" bs=1m count=2 2>/dev/null
run_expect 0 "parts" "case7 chunked backup" env ARCA_CHUNK_MB=1 "$ARCA" backup
parts="$(json_get "$work/vault/manifest.json" "d['_memories-private']['parts']")"
[ "$parts" -ge 2 ] 2>/dev/null || { echo "  MISMATCH (case7 parts=$parts < 2)"; fail=$((fail+1)); }
run_expect 0 "restored _memories-private" "case7 chunked restore" env ARCA_CHUNK_MB=1 "$ARCA" restore _memories-private "$work/restore7"
cmp -s "$work/ws/_memories-private/seed.bin" "$work/restore7/_memories-private/seed.bin" \
  || { echo "  MISMATCH (case7 restore bytes differ)"; fail=$((fail+1)); }

# ── Case 8: pack crosses ARCA_MAX_MB → backup auto-cuts generation -g2 as a ROOT commit ──
arca_before="$(git --git-dir="$work/gh/organvm/arca.git" rev-parse main)"
mkdir -p "$work/gh/disk"
printf '104857600' > "$work/gh/disk/organvm_arca"   # 100 GB (KB) → 102400 MB ≫ 512
run_expect 0 "rotating" "case8 auto-rotation" env ARCA_MAX_MB=512 "$ARCA" backup
[ "$(json_get "$work/vault/manifest.json" "d['_generation']['current']")" = "2" ] \
  || { echo "  MISMATCH (case8 gen current != 2)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_generation']['repo']")" = "organvm/arca-g2" ] \
  || { echo "  MISMATCH (case8 gen repo)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_generations'][0]['repo']")" = "organvm/arca" ] \
  || { echo "  MISMATCH (case8 archived repo)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault/manifest.json" "d['_finance-private']['gen']")" = "2" ] \
  || { echo "  MISMATCH (case8 store re-sealed into gen 2)"; fail=$((fail+1)); }
roots="$(git -C "$work/vault" rev-list --max-parents=0 HEAD | wc -l | tr -d ' ')"
[ "$roots" = "1" ] || { echo "  MISMATCH (case8 new gen is not a root commit: $roots roots)"; fail=$((fail+1)); }
[ "$(git -C "$work/vault" remote get-url origin)" = "file://$work/gh/organvm/arca-g2.git" ] \
  || { echo "  MISMATCH (case8 vault remote not re-pointed)"; fail=$((fail+1)); }
git --git-dir="$work/gh/organvm/arca-g2.git" rev-parse main >/dev/null 2>&1 \
  || { echo "  MISMATCH (case8 new repo never got the push)"; fail=$((fail+1)); }
[ "$(git --git-dir="$work/gh/organvm/arca.git" rev-parse main)" = "$arca_before" ] \
  || { echo "  MISMATCH (case8 archived repo was mutated)"; fail=$((fail+1)); }

# ── Case 9: rotate on a vault-less env seeds a fresh generation and archives the env repo ──
mkdir -p "$work/ws2/_collab-private"
printf 'memos\n' > "$work/ws2/_collab-private/notes.txt"
run_expect 0 "no working vault — archiving organvm/arcaseed and seeding" "case9 rotate seed" \
  env ARCA_WORKSPACE="$work/ws2" ARCA_VAULT_DIR="$work/vault2" ARCA_REPO=organvm/arcaseed "$ARCA" rotate
[ "$(json_get "$work/vault2/manifest.json" "d['_generation']['current']")" = "2" ] \
  || { echo "  MISMATCH (case9 seed gen current != 2)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault2/manifest.json" "d['_generation']['repo']")" = "organvm/arcaseed-g2" ] \
  || { echo "  MISMATCH (case9 seed gen repo)"; fail=$((fail+1)); }
[ "$(json_get "$work/vault2/manifest.json" "d['_collab-private']['gen']")" = "2" ] \
  || { echo "  MISMATCH (case9 store gen)"; fail=$((fail+1)); }
git --git-dir="$work/gh/organvm/arcaseed-g2.git" rev-parse main >/dev/null 2>&1 \
  || { echo "  MISMATCH (case9 seeded repo never pushed)"; fail=$((fail+1)); }

# ── Case 10: status distinguishes current / never-sealed ──
mkdir -p "$work/ws2/_life-private"
printf 'life\n' > "$work/ws2/_life-private/x"
run_expect 0 "NEVER sealed" "case10a status never-sealed" \
  env ARCA_WORKSPACE="$work/ws2" ARCA_VAULT_DIR="$work/vault2" ARCA_REPO=organvm/arcaseed "$ARCA" status
out="$(env ARCA_WORKSPACE="$work/ws2" ARCA_VAULT_DIR="$work/vault2" ARCA_REPO=organvm/arcaseed "$ARCA" status 2>&1)"
printf '%s\n' "$out" | grep -q "✓ _collab-private — current" && pass=$((pass+1)) \
  || { echo "  MISMATCH (case10b current store not marked current)"; printf '%s\n' "$out" | sed 's/^/    /'; fail=$((fail+1)); }

# ── Case 11: the freshness sensor follows the manifest's _generation.repo ──
out="$(python3 "$ROOT/scripts/arca-freshness.py" --vault-dir "$work/vault2" --json 2>&1)"; rc=$?
if [ "$rc" = "0" ] && printf '%s\n' "$out" | grep -q '"repo": "organvm/arcaseed-g2"' \
   && printf '%s\n' "$out" | grep -q '"ok": true'; then
  pass=$((pass+1))
else
  echo "  MISMATCH (case11 sensor does not follow manifest): rc=$rc"; printf '%s\n' "$out" | sed 's/^/    /'; fail=$((fail+1))
fi
out="$(python3 "$ROOT/scripts/arca-freshness.py" --vault-dir "$work/vault2" --repo organvm/explicit --json 2>&1)"
printf '%s\n' "$out" | grep -q '"repo": "organvm/explicit"' && pass=$((pass+1)) \
  || { echo "  MISMATCH (case11b explicit --repo ignored)"; fail=$((fail+1)); }

echo
if [ "$fail" -eq 0 ]; then
  echo "arca-generation.test.sh: PASS ($pass checks)"
else
  echo "arca-generation.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
