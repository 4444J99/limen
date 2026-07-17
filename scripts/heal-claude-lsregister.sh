#!/usr/bin/env bash
# heal-claude-lsregister.sh — clear a malformed, Gatekeeper-rejected ClaudeCode.app stub that
# LaunchServices keeps registered and macOS surfaces as:
#     "ClaudeCode.app is damaged and can't be opened. You should move it to Trash."
#
# ROOT (recurred 3×: 2026-06-24, 2026-07-04, 2026-07-17): an older Claude Code CLI shipped a
# URL-handler / TCC helper stub at ~/.local/share/claude/ClaudeCode.app. Its bundle SEAL is
# inconsistent — both `codesign --verify --strict` and `spctl` report exactly:
#     code has no resources but signature indicates they must be present
# so Gatekeeper treats it as "damaged". The dialog's own "Move to Trash" button RESEEDS the loop:
# it moves the broken stub into ~/.Trash where LaunchServices keeps it registered, so the next
# resolution of com.anthropic.claude-code hits the trashed copy and the same dialog fires again.
#
# The convergent cure is to UNREGISTER + REMOVE the stub (and any reseeded ~/.Trash copy), returning
# ClaudeCode.app registrations to their steady state of ZERO — CLI 2.1.190+ ships no .app stub; the
# CLI binary lives in versions/ and is never touched. Removing the stub also drops the mic/apple-events
# TCC identity it lent the CLI; that is the accepted 0-stub steady state — do NOT "restore" the stub.
#
# Only the EXACT known-malformed seal is reaped: a healthy stub (a future CLI may ship a properly
# sealed helper) passes codesign and is left registered. Never touches /Applications, ~/Applications,
# the versions/ dir, or the resolved CLI symlink target.
#
# Dry-run by default (reports the cure, mutates nothing). Arm with LIMEN_CLAUDE_LSREGISTER_HEAL=1 to
# apply — the launch-agent-liveness.py LIMEN_LAUNCHAGENT_HEAL convention (arm once in ~/.limen.env).
# Idempotent. Exit 0 ⟺ zero malformed ClaudeCode.app registrations remain (or none were found on a
# dry-run); exit 1 if malformed registrations remain, or a dry-run found some to cure (beat signal).
set -uo pipefail

if [ "$(uname 2>/dev/null)" != "Darwin" ]; then
  echo "claude-lsregister-heal: non-darwin — inapplicable"
  exit 0
fi

LSREG="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Support/lsregister"
CLAUDE_SHARE="${HOME}/.local/share/claude"
VERSIONS_DIR="${CLAUDE_SHARE}/versions"
TRASH="${HOME}/.Trash"
CLI_TARGET="$(readlink -f "${HOME}/.local/bin/claude" 2>/dev/null || true)"
MALFORMED='code has no resources but signature indicates they must be present'

if [ ! -x "$LSREG" ]; then
  echo "claude-lsregister-heal: lsregister not found — inapplicable"
  exit 0
fi

ARMED=0
[ "${LIMEN_CLAUDE_LSREGISTER_HEAL:-0}" = 1 ] && ARMED=1

# Every ClaudeCode.app path LaunchServices currently has registered.
enumerate() {
  "$LSREG" -dump 2>/dev/null \
    | grep -oE '/[^ ()]*ClaudeCode\.app' \
    | sort -u
}

# True iff $1 is a stub we are allowed to reap: a safe-prefix path (never the CLI or versions/)
# whose bundle fails codesign with the EXACT known-malformed seal string. A healthy stub is skipped.
condemnable() {
  local p="$1" out
  case "$p" in "$CLAUDE_SHARE"/*|"$TRASH"/*) : ;; *) return 1 ;; esac
  [ -n "$CLI_TARGET" ] && [ "$p" = "$CLI_TARGET" ] && return 1
  case "$p" in "$VERSIONS_DIR"/*) return 1 ;; esac
  out="$(codesign --verify --strict "$p" 2>&1 || true)"
  case "$out" in *"$MALFORMED"*) return 0 ;; *) return 1 ;; esac
}

found=0

# 1) Registered malformed stubs under the safe prefixes.
while IFS= read -r p; do
  [ -n "$p" ] || continue
  condemnable "$p" || continue
  found=$((found + 1))
  if [ "$ARMED" = 1 ]; then
    "$LSREG" -u "$p" 2>/dev/null || true
    rm -rf "$p" && echo "claude-lsregister-heal: unregistered + removed $p"
  else
    echo "claude-lsregister-heal: would unregister + remove: $p"
  fi
done <<EOF
$(enumerate)
EOF

# 2) ~/.Trash reseed sweep — the "Move to Trash" trap. find, never a raw glob (zsh nullglob errors
#    on an empty match). Any *ClaudeCode*.app in the Trash is an unwanted reseed, removed by name.
if [ -d "$TRASH" ]; then
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    found=$((found + 1))
    if [ "$ARMED" = 1 ]; then
      "$LSREG" -u "$t" 2>/dev/null || true
      rm -rf "$t" && echo "claude-lsregister-heal: swept trashed copy $t"
    else
      echo "claude-lsregister-heal: would sweep trashed copy: $t"
    fi
  done <<EOF
$(find "$TRASH" -maxdepth 1 -name '*ClaudeCode*.app' 2>/dev/null)
EOF
fi

# 3) Re-verify: how many malformed registrations survive?
remaining=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  condemnable "$p" && remaining=$((remaining + 1))
done <<EOF
$(enumerate)
EOF

if [ "$remaining" -eq 0 ] && { [ "$ARMED" = 1 ] || [ "$found" -eq 0 ]; }; then
  echo "claude-lsregister-heal: clean (0 malformed ClaudeCode.app registrations)"
  exit 0
fi
if [ "$ARMED" != 1 ]; then
  echo "claude-lsregister-heal: found $found malformed registration(s) — arm LIMEN_CLAUDE_LSREGISTER_HEAL=1 and re-run to cure"
  exit 1
fi
echo "claude-lsregister-heal: $remaining malformed registration(s) still present after cure"
exit 1
