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
#   6. Commit + push ciphertext only to a PRIVATE GitHub repo (default: organvm/arca).
#      GitHub never sees a plaintext byte; the vault repo's history is the offsite,
#      versioned, visible receipt lane for private-estate work. Unpushed seal commits
#      (e.g. a rejected push) are retried on every subsequent run, changed or not.
#
# VERBS:
#   arca.sh backup             — sweep all stores, push what changed (default; beat-wired)
#   arca.sh restore <store> [dest]  — decrypt a store to <dest> (default ~/arca-restore/)
#   arca.sh status             — manifest vs local: what's covered, what's stale
#
# Config (env): ARCA_WORKSPACE, ARCA_REPO, ARCA_VAULT_DIR, ARCA_KEY_SERVICE, ARCA_MAX_MB,
# ARCA_CHUNK_MB. Exit 0 ⟺ every store is backed up current (or nothing to do). Idempotent:
# a re-run with no changes makes no commits.
set -euo pipefail

WORKSPACE="${ARCA_WORKSPACE:-$HOME/Workspace}"
VAULT_REPO="${ARCA_REPO:-organvm/arca}"
VAULT_DIR="${ARCA_VAULT_DIR:-$HOME/.arca-vault}"
KEY_SERVICE="${ARCA_KEY_SERVICE:-limen-arca-vault}"
MAX_MB="${ARCA_MAX_MB:-512}"
CHUNK_MB="${ARCA_CHUNK_MB:-90}"   # per-blob ceiling; GitHub hard-rejects files >100MB
CMD="${1:-backup}"

log() { echo "arca: $*"; }
die() { echo "arca: FATAL: $*" >&2; exit 1; }

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
  local s="$1"
  {
    find "$s" -type f ! -path '*/.git/*' -print0 | sort -z | xargs -0 shasum -a 256 2>/dev/null || true
    git -C "$s" rev-parse HEAD 2>/dev/null || true
  } | shasum -a 256 | cut -d' ' -f1
}

manifest_get() { # manifest_get <name> <field>
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" <<'PY'
import json, sys, os
path, name, field = sys.argv[1:4]
m = json.load(open(path)) if os.path.exists(path) else {}
print(m.get(name, {}).get(field, ""))
PY
}

manifest_set() { # manifest_set <name> <hash> <bytes> <parts>   (parts 0 = single .tar.enc)
  python3 - "$VAULT_DIR/manifest.json" "$1" "$2" "$3" "$4" <<'PY'
import json, sys, os, datetime
path, name, digest, nbytes, parts = sys.argv[1:6]
m = json.load(open(path)) if os.path.exists(path) else {}
m[name] = {"hash": digest, "bytes": int(nbytes), "parts": int(parts),
           "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump(m, open(path, "w"), indent=1, sort_keys=True)
PY
}

ensure_vault() {
  if [ ! -d "$VAULT_DIR/.git" ]; then
    gh repo view "$VAULT_REPO" >/dev/null 2>&1 \
      || gh repo create "$VAULT_REPO" --private \
           -d "ARCA — encrypted private-estate vault (ciphertext only; key lives in the owner's Keychain)" >/dev/null \
      || die "cannot create private vault repo $VAULT_REPO"
    git clone -q "https://github.com/$VAULT_REPO.git" "$VAULT_DIR" || die "cannot clone $VAULT_REPO"
  fi
  git -C "$VAULT_DIR" pull --ff-only -q 2>/dev/null || true
  # Belt-and-braces: refuse to ever operate on a public vault.
  [ "$(gh repo view "$VAULT_REPO" --json visibility -q .visibility 2>/dev/null)" = "PRIVATE" ] \
    || die "vault repo $VAULT_REPO is not PRIVATE — refusing to push ciphertext anywhere public"
}

cmd_backup() {
  ensure_vault
  local key="" changed=0 name h old tmp size_mb enc_bytes parts parts_note
  for s in "$WORKSPACE"/_*-private; do
    [ -d "$s" ] || continue
    name=$(basename "$s")
    size_mb=$(( $(du -sk "$s" | cut -f1) / 1024 ))
    if [ "$size_mb" -gt "$MAX_MB" ]; then
      log "SKIPPED $name — ${size_mb}MB exceeds ARCA_MAX_MB=$MAX_MB (raise the cap or split the store; a silent skip would read as covered, so this line is the alarm)"
      continue
    fi
    h=$(store_hash "$s")
    old=$(manifest_get "$name" hash)
    [ "$h" = "$old" ] && continue
    [ -n "$key" ] || key=$(vault_key)
    tmp=$(mktemp -d)
    tar -C "$WORKSPACE" -cf "$tmp/$name.tar" "$name"
    ARCA_KEY="$key" openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -in "$tmp/$name.tar" -out "$VAULT_DIR/$name.tar.enc" -pass env:ARCA_KEY
    # Trust nothing unverified: decrypt and byte-compare before recording it as covered.
    ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$VAULT_DIR/$name.tar.enc" -out "$tmp/roundtrip.tar" -pass env:ARCA_KEY
    cmp -s "$tmp/$name.tar" "$tmp/roundtrip.tar" || die "roundtrip verify FAILED for $name — ciphertext untrusted, aborting before commit"
    enc_bytes=$(stat -f%z "$VAULT_DIR/$name.tar.enc")
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
    manifest_set "$name" "$h" "$enc_bytes" "$parts"
    rm -rf "$tmp"
    parts_note=""; [ "$parts" -gt 0 ] && parts_note=", $parts parts"
    log "sealed $name ($(( enc_bytes / 1024 / 1024 ))MB ciphertext${parts_note}, roundtrip verified)"
    changed=1
  done
  # -A stages deletions too (monolith→parts transitions and vice versa); the vault is a
  # machine-owned ciphertext repo, so the pathspec keeps this surgical anyway.
  if [ "$changed" = "1" ]; then
    git -C "$VAULT_DIR" add -A -- '*.tar.enc*' manifest.json
    git -C "$VAULT_DIR" commit -q -m "arca: seal $(date -u '+%F %TZ')"
  fi
  # Push whatever is unpushed — this run's seal AND any seal a previous run committed but
  # failed to push (the "retry next beat" promise lives here, not in the failure message).
  if [ -n "$(git -C "$VAULT_DIR" log --oneline '@{u}..HEAD' 2>/dev/null || true)" ]; then
    [ "$changed" = "1" ] || log "retrying unpushed seal commit(s) from a previous run"
    git -C "$VAULT_DIR" push -q origin HEAD || die "push failed — ciphertext committed locally, will retry next beat"
    log "vault pushed → $VAULT_REPO"
  elif [ "$changed" = "0" ]; then
    log "everything current — nothing to seal"
  fi
}

cmd_restore() {
  local name="${1:?usage: arca.sh restore <store> [dest]}"
  local dest="${2:-$HOME/arca-restore}"
  ensure_vault
  [ -f "$VAULT_DIR/$name.tar.enc" ] || ls "$VAULT_DIR/$name.tar.enc.part."* >/dev/null 2>&1 \
    || die "no sealed copy of $name in the vault"
  local key tmp; key=$(vault_key); tmp=$(mktemp -d); mkdir -p "$dest"
  if [ -f "$VAULT_DIR/$name.tar.enc" ]; then
    ARCA_KEY="$key" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -in "$VAULT_DIR/$name.tar.enc" -out "$tmp/$name.tar" -pass env:ARCA_KEY
  else
    # Alphabetic split suffixes glob in order, so cat reassembles the exact monolith.
    cat "$VAULT_DIR/$name.tar.enc.part."* | ARCA_KEY="$key" openssl enc -d -aes-256-cbc \
      -pbkdf2 -iter 200000 -out "$tmp/$name.tar" -pass env:ARCA_KEY
  fi
  tar -C "$dest" -xf "$tmp/$name.tar"
  rm -rf "$tmp"
  chmod 700 "$dest/$name"
  log "restored $name → $dest/$name (mode 700). Live stores are NEVER overwritten in place — move it yourself if that's the intent."
}

cmd_status() {
  ensure_vault
  local name h old when
  for s in "$WORKSPACE"/_*-private; do
    [ -d "$s" ] || continue
    name=$(basename "$s"); h=$(store_hash "$s"); old=$(manifest_get "$name" hash); when=$(manifest_get "$name" updated)
    if [ -z "$old" ]; then echo "  ✗ $name — NEVER sealed"
    elif [ "$h" = "$old" ]; then echo "  ✓ $name — current (sealed $when)"
    else echo "  Δ $name — CHANGED since seal $when (next backup will re-seal)"
    fi
  done
}

case "$CMD" in
  backup)  cmd_backup ;;
  restore) shift; cmd_restore "$@" ;;
  status)  cmd_status ;;
  *) die "unknown verb '$CMD' (backup|restore|status)" ;;
esac
