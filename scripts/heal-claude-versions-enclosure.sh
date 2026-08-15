#!/usr/bin/env bash
# heal-claude-versions-enclosure.sh — keep the Claude Code version store ENCLOSED in the stable
# ClaudeCode.app bundle so every per-version binary resolves to the one durable TCC identity.
#
# ROOT (2026-08-15, #1703 Track C receipts). macOS TCC names a disclaimed process by the bundle
# enclosing the path it was exec'd from. Non-spare pty-hosts re-exec themselves into the bundle
# (vendor Vsm(): execve(bundleExec, ..., {macDisclaimResponsibility:true})), but SPARE pty-hosts
# skip that re-exec (`if(!r) await Vsm()` — the `--bg-spare` branch), stay on their
# `versions/<v>` exec path, and every background session claimed from a pre-warmed spare
# therefore prompts as an app named "2.1.233" — a fresh TCC path-client per version, re-asking
# the full ~9-service grant set after every vendor update. The session argv is composed inside
# the signed vendor binary and cannot be redirected from outside (see the scope note in
# scripts/claude-identity-bundle.py) — but the FILESYSTEM under that argv is ours: with the
# store at ClaudeCode.app/Contents/MacOS/versions and a symlink at the old path, the kernel
# resolves the same literal argv to a bundle-enclosed executable, and every lane (daemon,
# spares, interactive launches, sessions) converges on com.anthropic.claude-code — the dialog
# reads "Claude Code", grants are answered once ever, and they survive updates because the
# binary is Developer-ID signed by the same identity each release. Upstream fix tracked at
# anthropics/claude-code#86706; this enclosure is the local cure until — and is harmless
# after — it ships.
#
# The vendor updater/installer may recreate `versions` as a real directory (it already
# re-points the ~/.local/bin/claude symlink on every update); this healer detects that reset
# and re-encloses on the next beat. It NEVER deletes a version binary, never edits TCC, never
# signs or re-links a vendor bundle. On a name collision whose two files differ it aborts
# loudly rather than choose. Running processes are unaffected: rename() preserves inodes.
#
# Dry-run by default (reports the cure, mutates nothing). Arm with
# LIMEN_CLAUDE_VERSIONS_ENCLOSURE_HEAL=1 or --apply (the sensor-injected arm, sensors.yaml
# 0g8b). Idempotent. Exit 0 <=> store enclosed (or inapplicable); exit 1 <=> heal needed
# (dry-run finding) or heal failed.
set -uo pipefail

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }

if [ "$(uname 2>/dev/null)" != "Darwin" ]; then
  log "claude-versions-enclosure: non-darwin — inapplicable"
  exit 0
fi

# LIMEN_CLAUDE_STORE is a test seam (point the whole code path at a fixture store). Unset in
# production — the vendor store location is fixed by the native installer.
STORE="${LIMEN_CLAUDE_STORE:-$HOME/.local/share/claude}"
BUNDLE="$STORE/ClaudeCode.app"
TARGET="$BUNDLE/Contents/MacOS/versions"
LINK="$STORE/versions"
REL_TARGET="ClaudeCode.app/Contents/MacOS/versions"

ARMED=0
[ "${LIMEN_CLAUDE_VERSIONS_ENCLOSURE_HEAL:-0}" = 1 ] && ARMED=1
[ "${1:-}" = "--apply" ] && ARMED=1

if [ ! -d "$BUNDLE/Contents/MacOS" ]; then
  # The vendor's _jb() materializes the bundle on every start; a missing bundle means no claude
  # has run yet on this store — nothing to enclose into, and inventing the bundle ourselves is
  # exactly what claude-identity-bundle.py exists to do correctly.
  log "claude-versions-enclosure: no ClaudeCode.app bundle at $BUNDLE — inapplicable until the vendor materializes it"
  exit 0
fi

# GREEN: LINK is a symlink resolving to TARGET, and TARGET is a real directory.
if [ -L "$LINK" ]; then
  RES="$(readlink "$LINK")"
  if { [ "$RES" = "$REL_TARGET" ] || [ "$RES" = "$TARGET" ]; } && [ -d "$TARGET" ] && [ ! -L "$TARGET" ]; then
    log "claude-versions-enclosure: enclosed ($LINK -> $RES)"
    exit 0
  fi
  log "claude-versions-enclosure: NOT GREEN — $LINK is a symlink to '$RES' (expected $REL_TARGET); unrecognized layout, refusing to guess"
  exit 1
fi

if [ ! -e "$LINK" ]; then
  # No store at all (mid-install window, or a reset that removed it). If the enclosed store
  # exists the cure is just the symlink; otherwise there is nothing to do yet.
  if [ -d "$TARGET" ]; then
    if [ "$ARMED" = 1 ]; then
      ln -s "$REL_TARGET" "$LINK" && { log "claude-versions-enclosure: restored $LINK -> $REL_TARGET"; exit 0; }
      log "claude-versions-enclosure: FAILED to create $LINK"
      exit 1
    fi
    log "claude-versions-enclosure: would restore $LINK -> $REL_TARGET — arm LIMEN_CLAUDE_VERSIONS_ENCLOSURE_HEAL=1 to cure"
    exit 1
  fi
  log "claude-versions-enclosure: no version store present — inapplicable"
  exit 0
fi

if [ ! -d "$LINK" ]; then
  log "claude-versions-enclosure: NOT GREEN — $LINK exists but is neither a directory nor a symlink; unrecognized layout, refusing to guess"
  exit 1
fi

# LINK is a real directory: the vendor layout (first run) or an updater/installer reset.
pending=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  pending=$((pending + 1))
done <<EOF
$(find "$LINK" -mindepth 1 -maxdepth 1 2>/dev/null)
EOF

if [ "$ARMED" != 1 ]; then
  log "claude-versions-enclosure: would enclose $pending entr(y|ies) from $LINK into $TARGET and symlink the old path — arm LIMEN_CLAUDE_VERSIONS_ENCLOSURE_HEAL=1 to cure"
  exit 1
fi

mkdir -p "$TARGET" || { log "claude-versions-enclosure: FAILED mkdir $TARGET"; exit 1; }

moved=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  base="$(basename "$f")"
  dest="$TARGET/$base"
  if [ ! -e "$dest" ]; then
    mv "$f" "$dest" || { log "claude-versions-enclosure: FAILED to move $base"; exit 1; }
    moved=$((moved + 1))
  elif [ "$f" -ef "$dest" ]; then
    # Same inode via hardlink — the duplicate directory entry is redundant, drop only the LINK-side name.
    rm "$f" || { log "claude-versions-enclosure: FAILED to drop hardlink duplicate $base"; exit 1; }
  elif [ "$(stat -f %z "$f" 2>/dev/null)" = "$(stat -f %z "$dest" 2>/dev/null)" ]; then
    # Byte-identical size at the same version name: the enclosed copy already serves; drop the reset's copy.
    rm "$f" || { log "claude-versions-enclosure: FAILED to drop duplicate $base"; exit 1; }
  else
    log "claude-versions-enclosure: CONFLICT — $base exists in both stores with different sizes; refusing to choose (resolve by hand, then re-run)"
    exit 1
  fi
done <<EOF
$(find "$LINK" -mindepth 1 -maxdepth 1 2>/dev/null)
EOF

rmdir "$LINK" || { log "claude-versions-enclosure: FAILED — $LINK not empty after enclosure; leaving both stores in place"; exit 1; }
ln -s "$REL_TARGET" "$LINK" || { log "claude-versions-enclosure: FAILED to create $LINK symlink after enclosure"; exit 1; }
log "claude-versions-enclosure: enclosed $moved entr(y|ies); $LINK -> $REL_TARGET"
exit 0
