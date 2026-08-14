#!/usr/bin/env bash
# arca.sh — ARCA (Latin: strongbox): encrypted off-machine backup of the private estate.
#
# THE PROBLEM IT CLOSES: the private stores (~/Workspace/_*-private — health chart, legal
# docket, people room, finance, life) are mode-700 / no-remote BY DESIGN, which protects
# against leaks but not against loss: one dead Mac and the whole private estate is gone.
# "Private" must mean processed + ENCRYPTED + backed up — not unbacked-up.
#
# THE PROTOCOL (applies to every current AND future _*-private store — the glob is the
# registry, so a new store is covered the day it is created):
#   1. Detect change per store (content hash of all files ex .git + git HEAD if present).
#   2. tar the whole store (including .git history where present).
#   3. Encrypt: AES-256-CBC, PBKDF2 200k iterations. The key lives ONLY in the macOS
#      Keychain (service: limen-arca-vault) — auto-generated on first run, NEVER printed,
#      never in any repo or env file. Escrow of the key off-machine is a his-hand lever
#      (L-ARCA-KEY-ESCROW) — until pulled, restore requires this Mac's Keychain.
#   4. Verify the roundtrip (decrypt + byte-compare) BEFORE trusting the ciphertext.
#   5. Chunk: ciphertext over ARCA_CHUNK_MB (default 90) is split into <name>.tar.enc.part.*
#      pieces so no single blob crosses GitHub's hard 100MB file limit; reassembly is
#      byte-verified against the monolith before the monolith is dropped. Alphabetic
#      split suffixes glob back in order, so restore is just `cat parts | decrypt`.
#   6. Commit + push ciphertext only to a PRIVATE GitHub repo. GitHub never sees a
#      plaintext byte; the vault repo's history is the offsite, versioned, visible receipt
#      lane for private-estate work. Unpushed seal commits (e.g. a rejected push) are
#      retried on every subsequent run, changed or not.
#
# GENERATIONS (POTESTAS 0.3, organvm/limen#2089): the vault repo is not one eternal history.
# Each GENERATION is one private repo (organvm/arca → organvm/arca-g2 → -g3 …); the manifest
# records the current generation and every archived one, so restore still resolves a store to
# the generation that holds it. Rotation is the root-cause fix for the >19 GB clone death
# (#2072): the old vault grew without bound because every changed beat committed a full tar of
# every store into one history forever. A working vault is now cloned with `--depth 1` (the tip
# is all a backup needs — history is the archive's job), and when a generation's pack crosses
# ARCA_MAX_MB the next generation is cut as a fresh ROOT commit, so no generation ever inherits
# another's growth. organvm/arca is left byte-identical as a cold archive — nothing is ever
# repaired, rewritten, pruned, or deleted.
#
# VERBS (one is REQUIRED — a bare invocation prints this list and exits 2):
#   arca.sh backup             — sweep all stores, push what changed (beat-wired); auto-
#                                 cuts a new generation when the pack crosses ARCA_MAX_MB
#   arca.sh rotate [next-repo] — cut a NEW generation NOW (seed a fresh vault + archive the
#                                 current repo if no working vault exists yet)
#   arca.sh restore <store> [dest]  — decrypt a store to <dest> (default ~/arca-restore/)
#   arca.sh status             — manifest vs local: what's covered, what's stale
#   arca.sh seal <src> <out.enc>    — one-off envelope: tar+encrypt any file/dir, roundtrip
#                                     verified; no vault/manifest/git (HORREVM custody lane)
#   arca.sh unseal <in.enc> <dest>  — decrypt a one-off envelope, extract into <dest>
#
# Config (env): ARCA_WORKSPACE, ARCA_REPO, ARCA_VAULT_DIR, ARCA_KEY_SERVICE, ARCA_MAX_MB,
# ARCA_CHUNK_MB, ARCA_CLONE_URL_BASE. ARCA_REPO names the CURRENT generation repo when
# seeding; once a working vault exists the manifest's `_generation.repo` is authoritative.
# ARCA_MAX_MB is a dual knob: the per-store skip cap AND the vault-pack threshold that cuts
# the next generation. Exit 0 ⟺ every store is backed up current (or nothing to do).
# Idempotent: a re-run with no changes makes no commits.
set -euo pipefail

WORKSPACE="${ARCA_WORKSPACE:-$HOME/Workspace}"
VAULT_REPO="${ARCA_REPO:-organvm/arca}"
VAULT_DIR="${ARCA_VAULT_DIR:-$HOME/.arca-vault}"
KEY_SERVICE="${ARCA_KEY_SERVICE:-limen-arca-vault}"
MAX_MB="${ARCA_MAX_MB:-512}"
CHUNK_MB="${ARCA_CHUNK_MB:-90}"   # per-blob ceiling; GitHub hard-rejects files >100MB
CLONE_URL_BASE="${ARCA_CLONE_URL_BASE:-https://github.com}"  # test hook: hermetic file:// remotes
# A VERB IS REQUIRED. This used to default to `backup`, which meant typing `arca.sh` to see what it
# does silently STARTED A BACKUP — sweeping every ~/Workspace/_*-private store, encrypting, and
# pushing ciphertext to a private remote. There was no --help either (it hit the unknown-verb `die`),
# so the natural way to ask "what are the verbs?" was the one input that ran the destructive-ish path.
# Measured 2026-07-29 by doing exactly that. The only caller in the estate is metabolize.sh:115,
# which passes `backup` explicitly, so requiring the verb costs nothing and closes the trap.
CMD="${1:-}"

log() { echo "arca: $*"; }
die() { echo "arca: FATAL: $*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
arca.sh — encrypted private-estate vault. A VERB IS REQUIRED.

  arca.sh backup                  sweep all stores, push what changed (beat-wired)
  arca.sh rotate [next-repo]      cut a NEW generation NOW (seed if no working vault exists)
  arca.sh restore <store> [dest]  decrypt a store to <dest> (default ~/arca-restore/)
  arca.sh status                  manifest vs local: what's covered, what's stale
  arca.sh seal <src> <out.enc>    one-off envelope: tar+encrypt, roundtrip verified
  arca.sh unseal <in.enc> <dest>  decrypt a one-off envelope into <dest>

Config (env): ARCA_WORKSPACE, ARCA_REPO, ARCA_VAULT_DIR, ARCA_KEY_SERVICE, ARCA_MAX_MB,
ARCA_CHUNK_MB, ARCA_CLONE_URL_BASE. Generations: the manifest owns the CURRENT generation
once a vault exists; ARCA_MAX_MB is both the per-store skip cap and the pack threshold that
cuts the next generation.
USAGE
}

case "$CMD" in
  -h | --help | help)
    usage
    exit 0
    ;;
  "")
    # stderr + nonzero: a caller that relied on the old implicit default must FAIL LOUDLY here
    # rather than silently do nothing, which would be a different and quieter bug.
    usage >&2
    exit 2
    ;;
esac

vault_key() {
  # Fetch (or first-run: generate) the vault key. The value is captured by callers into a
  # local var and handed to openssl via env — it is never echoed, logged, or written to disk.
  security find-generic-password -s "$KEY_SERVICE" -w 2>/dev/null && return 0
  security add-generic-password -s "$KEY_SERVICE" -a "$USER" -w "$(openssl rand -hex 32)" >/dev/null \
    || die "cannot create vault key in Keychain (locked? headless?)"
  log "new vault key generated in Keychain (service: $KEY_SERVICE) — escrow it: lever L-ARCA-KEY-ESCROW" >&2
  security find-generic-password -s "$KEY_SERVICE" -w
}

store_hash() {
  # Content identity of a store: every file outside .git, plus the git HEAD if it is a repo
  # (so committed history counts as content). Stable across runs; changes ⟺ real change.
  # Portable hash: coreutils sha256sum (Linux) or perl shasum (macOS) — identical digests.
  local s="$1" hash_tool tmp
  if command -v sha256sum >/dev/null 2>&1; then hash_tool="sha256sum"; else hash_tool="shasum -a 256"; fi
  tmp=$(mktemp)
  {
    find "$s" -type f ! -path '*/.git/*' -print0 | sort -z | xargs -0 $hash_tool 2>/dev/null || true
    git -C "$s" rev-parse HEAD 2>/dev/null || true
  } > "$tmp"
  $hash_tool "$tmp" | cut -d' ' -f1
  rm -f "$tmp"
}

file_bytes() { # file_bytes <file> — portable byte count (wc -c works on BSD and GNU; stat -f%z is BSD-only)
  wc -c < "$1" | tr -d ' '
}

manifest_get() { # manifest_get <name> <field>
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" <<'PY'
import json, sys, os
path, name, field = sys.argv[1:4]
m = json.load(open(path)) if os.path.exists(path) else {}
print(m.get(name, {}).get(field, ""))
PY
}

manifest_set() { # manifest_set <name> <hash> <bytes> <parts> <gen>   (parts 0 = single .tar.enc)
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" "$3" "$4" "$5" <<'PY'
import json, sys, os, datetime
path, name, digest, nbytes, parts, gen = sys.argv[1:7]
m = json.load(open(path)) if os.path.exists(path) else {}
m[name] = {"hash": digest, "bytes": int(nbytes), "parts": int(parts), "gen": int(gen),
           "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump(m, open(path, "w"), indent=1, sort_keys=True)
PY
}

manifest_generation_set() { # manifest_generation_set <current> <repo> <generations-json>
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" "$3" <<'PY'
import json, sys, os, datetime
path, current, repo, gens_json = sys.argv[1:5]
m = json.load(open(path)) if os.path.exists(path) else {}
m["_generation"] = {"current": int(current), "repo": repo,
                    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
m["_generations"] = json.loads(gens_json)
json.dump(m, open(path, "w"), indent=1, sort_keys=True)
PY
}

manifest_generations_json() { # manifest_generations_json <repo> <gen> — archived list + this gen
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" <<'PY'
import json, sys, os, datetime
path, repo, gen = sys.argv[1:4]
m = json.load(open(path)) if os.path.exists(path) else {}
archived = list(m.get("_generations", []))
archived.append({"gen": int(gen), "repo": repo, "archived": True,
                 "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
print(json.dumps(archived))
PY
}

manifest_generation_repo() { # manifest_generation_repo <gen> → the repo that holds that generation
  python3 - "$VAULT_DIR/manifest.json" "$1" <<'PY'
import json, sys, os
path, gen = sys.argv[1:3]
if not gen.isdigit():
    print(""); sys.exit(0)
gen = int(gen)
m = json.load(open(path)) if os.path.exists(path) else {}
if m.get("_generation", {}).get("current") == gen:
    print(m["_generation"].get("repo", "")); sys.exit(0)
for g in m.get("_generations", []):
    if g.get("gen") == gen:
        print(g.get("repo", "")); sys.exit(0)
print("")
PY
}

gen_base_name() { # gen_base_name <repo> → repo with a trailing -g<N> suffix stripped
  printf '%s' "$1" | sed -E 's/-g[0-9]+$//'
}

vault_pack_mb() { # current generation's pack size in MB (GitHub-reported, includes history)
  gh repo view "$VAULT_REPO" --json diskUsage -q .diskUsage 2>/dev/null | awk '{print int($1/1024)}'
}

ensure_vault() {
  if [ ! -d "$VAULT_DIR/.git" ]; then
    gh repo view "$VAULT_REPO" >/dev/null 2>&1 \
      || gh repo create "$VAULT_REPO" --private --confirm \
           -d "ARCA — encrypted private-estate vault (ciphertext only; key lives in the owner's Keychain)" >/dev/null \
      || die "cannot create private vault repo $VAULT_REPO"
    # Depth 1: the tip is all a working vault needs — history is the archive's job (the old
    # full clone died past 19 GB, #2072). Rotating generations keeps that bounded.
    git clone -q --depth 1 "$CLONE_URL_BASE/$VAULT_REPO.git" "$VAULT_DIR" || die "cannot clone $VAULT_REPO"
    # A fresh clone of an empty repo carries no manifest — record generation 1 NOW so the
    # manifest is the source of truth from the first byte (the fleet-follows-manifest
    # property must hold even before the first rotation, else ensure_vault would re-resolve
    # "" and silently fall back to the env default forever).
    if [ ! -f "$VAULT_DIR/manifest.json" ]; then
      manifest_generation_set 1 "$VAULT_REPO" "[]"
    fi
  else
    # A working vault exists — the manifest is the source of truth for the CURRENT generation;
    # follow it even when the env default still names an archived generation.
    local manifest_repo
    manifest_repo=$(manifest_get _generation repo)
    [ -n "$manifest_repo" ] && VAULT_REPO="$manifest_repo"
  fi
  git -C "$VAULT_DIR" pull --ff-only -q 2>/dev/null || true
  # Belt-and-braces: refuse to ever operate on a public vault.
  [ "$(gh repo view "$VAULT_REPO" --json visibility -q .visibility 2>/dev/null)" = "PRIVATE" ] \
    || die "vault repo $VAULT_REPO is not PRIVATE — refusing to push ciphertext anywhere public"
}

seal_store() { # seal_store <name> <force> — seal one store into the current generation; sets changed=1
  local name="$1" force="$2" h old cur_gen tmp size_mb enc_bytes parts parts_note key=""
  [ -d "$WORKSPACE/$name" ] || return 0
  size_mb=$(( $(du -sk "$WORKSPACE/$name" | cut -f1) / 1024 ))
  if [ "$size_mb" -gt "$MAX_MB" ]; then
    log "SKIPPED $name — ${size_mb}MB exceeds ARCA_MAX_MB=$MAX_MB (raise the cap or split the store; a silent skip would read as covered, so this line is the alarm)"
    return 0
  fi
  h=$(store_hash "$WORKSPACE/$name")
  old=$(manifest_get "$name" hash)
  [ "$h" = "$old" ] && [ "$force" != "1" ] && return 0
  [ -n "$key" ] || key=$(vault_key)
  tmp=$(mktemp -d)
  tar -C "$WORKSPACE" -cf "$tmp/$name.tar" "$name"
  ARCA_KEY="$key" openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$tmp/$name.tar" -out "$VAULT_DIR/$name.tar.enc" -pass env:ARCA_KEY
  # Trust nothing unverified: decrypt and byte-compare before recording it as covered.
  ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$VAULT_DIR/$name.tar.enc" -out "$tmp/roundtrip.tar" -pass env:ARCA_KEY
  cmp -s "$tmp/$name.tar" "$tmp/roundtrip.tar" || die "roundtrip verify FAILED for $name — ciphertext untrusted, aborting before commit"
  enc_bytes=$(file_bytes "$VAULT_DIR/$name.tar.enc")
  # Chunk oversized ciphertext: GitHub hard-rejects any blob >100MB, so a big store must
  # ship as parts. Stale parts are cleared first so a shrunken store falls back to one file.
  rm -f "$VAULT_DIR/$name.tar.enc.part."*
  parts=0
  if [ "$enc_bytes" -gt $(( CHUNK_MB * 1024 * 1024 )) ]; then
    split -b "${CHUNK_MB}m" "$VAULT_DIR/$name.tar.enc" "$VAULT_DIR/$name.tar.enc.part."
    cat "$VAULT_DIR/$name.tar.enc.part."* | cmp -s - "$VAULT_DIR/$name.tar.enc" \
      || die "chunk reassembly verify FAILED for $name — parts untrusted, aborting before commit"
    rm -f "$VAULT_DIR/$name.tar.enc"
    parts=$(ls "$VAULT_DIR/$name.tar.enc.part."* | wc -l | tr -d ' ')
  fi
  cur_gen=$(manifest_get _generation current); cur_gen=${cur_gen:-1}
  manifest_set "$name" "$h" "$enc_bytes" "$parts" "$cur_gen"
  rm -rf "$tmp"
  parts_note=""; [ "$parts" -gt 0 ] && parts_note=", $parts parts"
  log "sealed $name ($(( enc_bytes / 1024 / 1024 ))MB ciphertext${parts_note}, roundtrip verified, gen $cur_gen)"
  changed=1
}

cut_generation() { # cut_generation [next-repo] — archive the current generation, prep a fresh one
  #                    re-points VAULT_REPO; the caller re-seals + pushes
  local cur_gen cur_repo base next_repo
  cur_repo="$VAULT_REPO"
  if [ -d "$VAULT_DIR/.git" ]; then
    cur_gen=$(manifest_get _generation current)
    cur_gen=${cur_gen:-1}
  else
    cur_gen=1
  fi
  next_repo="${1:-}"
  if [ -z "$next_repo" ]; then
    base=$(gen_base_name "$cur_repo")
    next_repo="${base}-g$(( cur_gen + 1 ))"
  fi
  [ "$next_repo" != "$cur_repo" ] || die "rotate would point the vault at its own repo ($cur_repo)"
  gh repo view "$next_repo" >/dev/null 2>&1 \
    || gh repo create "$next_repo" --private --confirm \
         -d "ARCA — encrypted private-estate vault, generation $(( cur_gen + 1 )) (ciphertext only; key lives in the owner's Keychain)" >/dev/null \
    || die "cannot create private vault repo $next_repo"
  if [ -d "$VAULT_DIR/.git" ]; then
    # In-place cut: abandon the current generation's history so the new one is a ROOT commit
    # (no generation ever inherits another's growth). The working tree is kept; the caller
    # re-seals every store into the fresh tree. The shallow marker is dropped too — it names a
    # commit that stops existing, and the new generation is a full root, not a shallow cut.
    git -C "$VAULT_DIR" remote set-url origin "$CLONE_URL_BASE/$next_repo.git"
    git -C "$VAULT_DIR" checkout -q --orphan "arca-gen$(( cur_gen + 1 ))"
    git -C "$VAULT_DIR" rm -rf --cached -q . 2>/dev/null || true
    git -C "$VAULT_DIR" branch -q -D main 2>/dev/null || true
    git -C "$VAULT_DIR" branch -q -m main
    rm -f "$VAULT_DIR/.git/shallow"
  else
    # Seed: no working vault yet — the current repo (env/default) becomes the archived
    # generation, and the fresh working copy is initialized for the new one.
    mkdir -p "$VAULT_DIR"
    git -C "$VAULT_DIR" init -q -b main
    git -C "$VAULT_DIR" remote add origin "$CLONE_URL_BASE/$next_repo.git"
  fi
  manifest_generation_set "$(( cur_gen + 1 ))" "$next_repo" "$(manifest_generations_json "$cur_repo" "$cur_gen")"
  VAULT_REPO="$next_repo"
  log "vault → generation $(( cur_gen + 1 )) in $next_repo ($cur_repo archived; re-sealing all stores)"
}

cmd_backup() {
  ensure_vault
  local key="" changed=0 force=0 pack_mb
  # Generation rotation (the root-cause fix, #2089): once the current generation's pack
  # crosses ARCA_MAX_MB, cut the next generation instead of growing one history forever.
  pack_mb=$(vault_pack_mb 2>/dev/null || echo 0)
  if [ "${pack_mb:-0}" -gt "$MAX_MB" ]; then
    log "generation $VAULT_REPO pack ${pack_mb}MB exceeds ARCA_MAX_MB=$MAX_MB — rotating"
    cut_generation ""
    force=1
  fi
  for s in "$WORKSPACE"/_*-private; do
    [ -d "$s" ] || continue
    seal_store "$(basename "$s")" "$force"
  done
  # -A stages deletions too (monolith→parts transitions and vice versa); the vault is a
  # machine-owned ciphertext repo, so the pathspec keeps this surgical anyway. A rotation
  # commits the generation metadata even if every store was already current.
  if [ "$changed" = "1" ] || [ "$force" = "1" ]; then
    git -C "$VAULT_DIR" add -A -- '*.tar.enc*' manifest.json
    git -C "$VAULT_DIR" commit -q -m "arca: seal $(date -u '+%F %TZ')"
    # A fresh clone of an empty repo has no upstream yet (and a freshly cut generation
    # points at a brand-new repo) — `push -u` establishes it and is a no-op on the
    # already-tracking case. Every commit THIS run is pushed: unpushed retries from a
    # previous run are covered by the origin/main branch below.
    git -C "$VAULT_DIR" push -q -u origin main || die "push failed — ciphertext committed locally, will retry next beat"
    log "vault pushed → $VAULT_REPO"
  elif [ -n "$(git -C "$VAULT_DIR" log --oneline 'origin/main..HEAD' 2>/dev/null || true)" ]; then
    # Push whatever is unpushed — a seal a previous run committed but failed to push (the
    # "retry next beat" promise lives here, not in the failure message). origin/main, not
    # @{u}: after a failed `push -u` the upstream is never recorded, but the remote ref is.
    log "retrying unpushed seal commit(s) from a previous run"
    git -C "$VAULT_DIR" push -q origin main || die "push failed — ciphertext committed locally, will retry next beat"
    log "vault pushed → $VAULT_REPO"
  elif [ "$changed" = "0" ]; then
    log "everything current — nothing to seal"
  fi
}

cmd_rotate() { # cmd_rotate [next-repo] — cut a new generation NOW (seed if no working vault exists)
  if [ ! -d "$VAULT_DIR/.git" ]; then
    log "no working vault — archiving $VAULT_REPO and seeding a fresh generation"
  fi
  cut_generation "${1:-}"
  for s in "$WORKSPACE"/_*-private; do
    [ -d "$s" ] || continue
    seal_store "$(basename "$s")" 1
  done
  git -C "$VAULT_DIR" add -A -- '*.tar.enc*' manifest.json
  git -C "$VAULT_DIR" commit -q -m "arca: rotate $(date -u '+%F %TZ')"
  git -C "$VAULT_DIR" push -q -u origin main || die "push failed — ciphertext committed locally, will retry next beat"
  log "vault pushed → $VAULT_REPO"
}

restore_from_vault() { # restore_from_vault <vault_dir> <store> <dest> — exit 0 if restored, 1 if absent
  local vault="$1" name="$2" dest="$3" key tmp
  [ -f "$vault/$name.tar.enc" ] || ls "$vault/$name.tar.enc.part."* >/dev/null 2>&1 || return 1
  key=$(vault_key); tmp=$(mktemp -d); mkdir -p "$dest"
  if [ -f "$vault/$name.tar.enc" ]; then
    ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$vault/$name.tar.enc" -out "$tmp/$name.tar" -pass env:ARCA_KEY
  else
    # Alphabetic split suffixes glob in order, so cat reassembles the exact monolith.
    cat "$vault/$name.tar.enc.part."* | ARCA_KEY="$key" openssl enc -d -aes-256-cbc \
      -pbkdf2 -iter 200000 -out "$tmp/$name.tar" -pass env:ARCA_KEY
  fi
  tar -C "$dest" -xf "$tmp/$name.tar"
  rm -rf "$tmp"
  chmod 700 "$dest/$name"
  log "restored $name → $dest/$name (mode 700). Live stores are NEVER overwritten in place — move it yourself if that's the intent."
}

cmd_restore() {
  local name="${1:?usage: arca.sh restore <store> [dest]}"
  local dest="${2:-$HOME/arca-restore}"
  ensure_vault
  restore_from_vault "$VAULT_DIR" "$name" "$dest" && return 0
  # Not in the current generation — resolve the store's archived generation and clone it.
  local gen repo tmp_vault
  gen=$(manifest_get "$name" gen)
  repo=$(manifest_generation_repo "$gen")
  [ -n "$gen" ] && [ -n "$repo" ] \
    || die "no sealed copy of $name in the current vault or any recorded generation"
  tmp_vault=$(mktemp -d)
  git clone -q --depth 1 "$CLONE_URL_BASE/$repo.git" "$tmp_vault" \
    || die "cannot clone generation $gen vault $repo — its ciphertext is not reachable"
  restore_from_vault "$tmp_vault" "$name" "$dest" \
    || die "no sealed copy of $name in generation $gen vault $repo"
  rm -rf "$tmp_vault"
}

cmd_status() { # cmd_status [--json] [--strict] — COVERAGE: does the vault hold what is on disk NOW?
  # This is the coverage half of the ARCA predicate, and it is deliberately distinct from
  # arca-freshness.py's *recency* half ("did the vault move lately?"). Recency alone cannot see
  # a store that changed after the last seal, nor one the cap SKIPPED, because the vault moved
  # for some OTHER store and went green. Both were live on 2026-08-12: three stores Δ and
  # _collaboration-operations-private (4.9GB vs ARCA_MAX_MB=512) NEVER sealed, while the beat's
  # arca-freshness sensor reported OK.
  #
  # --strict makes it a PREDICATE (exit 1 on any Δ/✗) so something other than a human reading a
  # 21MB log can consume it. Without --strict it stays the exit-0 display it has always been.
  local as_json=0 strict=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --json) as_json=1 ;;
      --strict) strict=1 ;;
      *) die "unknown status flag '$1' (--json|--strict)" ;;
    esac
    shift
  done
  # log() writes to STDOUT, and ensure_vault logs (seeding a manifest, recording a generation).
  # Under --json that would prepend prose to the payload and make it unparseable — a
  # machine-readable interface has to keep stdout pure, so its chatter goes to stderr instead.
  if [ "$as_json" = "1" ]; then ensure_vault 1>&2; else ensure_vault; fi
  local name h old when state stale=0 first=1
  if [ "$as_json" = "1" ]; then printf '{"schema":"limen.arca_coverage.v1","stores":['; fi
  for s in "$WORKSPACE"/_*-private; do
    [ -d "$s" ] || continue
    name=$(basename "$s"); h=$(store_hash "$s"); old=$(manifest_get "$name" hash); when=$(manifest_get "$name" updated)
    if [ -z "$old" ]; then state="never_sealed"; stale=1
    elif [ "$h" = "$old" ]; then state="current"
    else state="changed"; stale=1
    fi
    if [ "$as_json" = "1" ]; then
      [ "$first" = "1" ] || printf ','
      first=0
      # store NAMES only — never a path inside a store, never contents (same PII rule as the sensor)
      printf '{"name":"%s","state":"%s","sealed_at":"%s"}' "$name" "$state" "$when"
    else
      case "$state" in
        never_sealed) echo "  ✗ $name — NEVER sealed" ;;
        current)      echo "  ✓ $name — current (sealed $when)" ;;
        changed)      echo "  Δ $name — CHANGED since seal $when (next backup will re-seal)" ;;
      esac
    fi
  done
  if [ "$as_json" = "1" ]; then
    local ok_json=true
    if [ "$stale" = "1" ]; then ok_json=false; fi
    printf '],"ok":%s}\n' "$ok_json"
  fi
  if [ "$strict" = "1" ] && [ "$stale" = "1" ]; then return 1; fi
  return 0
}

cmd_seal() {
  # One envelope for the whole estate: HORREVM custody payloads reuse the exact backup
  # cipher + key so L-ARCA-KEY-ESCROW stays the single escrow liability (no rclone crypt).
  local src="${1:?usage: arca.sh seal <src> <out.enc>}"
  local out="${2:?usage: arca.sh seal <src> <out.enc>}"
  [ -e "$src" ] || die "seal source $src does not exist"
  local key tmp parent name
  key=$(vault_key); tmp=$(mktemp -d)
  parent=$(cd "$(dirname "$src")" && pwd); name=$(basename "$src")
  tar -C "$parent" -cf "$tmp/payload.tar" "$name"
  ARCA_KEY="$key" openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$tmp/payload.tar" -out "$out" -pass env:ARCA_KEY
  ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$out" -out "$tmp/roundtrip.tar" -pass env:ARCA_KEY
  cmp -s "$tmp/payload.tar" "$tmp/roundtrip.tar" \
    || die "roundtrip verify FAILED for $name — ciphertext untrusted"
  rm -rf "$tmp"
  log "sealed $name → $out ($(file_bytes "$out") bytes, roundtrip verified)"
}

cmd_unseal() {
  local in="${1:?usage: arca.sh unseal <in.enc> <dest>}"
  local dest="${2:?usage: arca.sh unseal <in.enc> <dest>}"
  [ -f "$in" ] || die "no ciphertext at $in"
  local key tmp; key=$(vault_key); tmp=$(mktemp -d); mkdir -p "$dest"
  ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$in" -out "$tmp/payload.tar" -pass env:ARCA_KEY
  tar -C "$dest" -xf "$tmp/payload.tar"
  rm -rf "$tmp"
  log "unsealed $(basename "$in") → $dest"
}

case "$CMD" in
  backup)  cmd_backup ;;
  rotate)  shift; cmd_rotate "$@" ;;
  restore) shift; cmd_restore "$@" ;;
  status)  shift; cmd_status "$@" ;;
  seal)    shift; cmd_seal "$@" ;;
  unseal)  shift; cmd_unseal "$@" ;;
  *) die "unknown verb '$CMD' (backup|rotate|restore|status|seal|unseal)" ;;
esac
