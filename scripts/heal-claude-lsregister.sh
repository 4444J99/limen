#!/usr/bin/env bash
# heal-claude-lsregister.sh — keep Claude Code's vendor-materialized ClaudeCode.app bundle INERT to
# Gatekeeper: present on disk for `exec`, absent from LaunchServices. macOS surfaces the registered
# form as:
#     "ClaudeCode.app is damaged and can't be opened. You should move it to Trash."
#
# ROOT — corrected 2026-08-05, reproduced from scratch. The prior header claimed this was a stale
# stub from a pre-2.1.190 CLI and that the steady state was ZERO bundles ("do NOT restore the stub").
# Both halves were false, and that false premise is why the dialog recurred ~10-15x across six weeks
# and five cures (#1206, #1219, #1242, #1704, #1837). The facts:
#
#   1. The bundle is Gatekeeper-invalid BY CONSTRUCTION, not by corruption. The CLI is a bare Mach-O
#      signed Developer ID with `Sealed Resources=none`. Wrapped in a hand-written .app, macOS
#      evaluates it as a BUNDLE and `--strict` demands a Contents/_CodeSignature/CodeResources the
#      signature never sealed. The SAME INODE passes bare (exit 0) and fails bundled (exit 1).
#   2. "Absent" is unreachable. The LIVE binary materializes it on every start — the vendor's own
#      `_jb()`: mkdir + writeFile(Info.plist) + link(process.execPath). Every removal guarantees the
#      next recreate, so deletion is a duty cycle, not a cure.
#   3. "Valid" is unreachable too. Contents/MacOS/claude is a HARDLINK to the live versions/<v>
#      binary, so re-signing the bundle would rewrite Anthropic's Developer ID signature on the
#      running CLI in place and break auto-update. Disqualified, not merely undesirable.
#   4. Deleting it also DESTROYS the stable TCC identity that scripts/claude-identity-bundle.py
#      (sensor 0g8d) exists to keep — the two organs held contradictory invariants over one file.
#
# THE CURE IS UNREGISTRATION, NOT REMOVAL. `execve` never consults LaunchServices; only the dialog
# does. So the reachable fixed point is: bundle PRESENT and inode-correct (0g8d's invariant, and the
# vendor's) while carrying ZERO LaunchServices registrations (this script's invariant). Those are two
# non-overlapping predicates over one file, so both organs can be green at once.
#
# Ideal form: IF-GATEKEEPER-INERT (docs/IDEAL-FORMS-LEDGER.md). Corrected root cause + provenance:
# docs/architecture/macos-tcc-gatekeeper-dialogs-solved.md.
#
# A bundle that PASSES codesign is left registered — a future vendor bundle that is properly sealed
# is not this script's business. Never touches /Applications, ~/Applications (the deep-link handler
# is the operator's feature trade — see lever L-CLAUDE-DEEPLINK-REGISTRATION), the versions/ dir, or
# the resolved CLI symlink target.
#
# The ~/.Trash sweep still REMOVES: a trashed copy is genuine garbage (the dialog's own "Move to
# Trash" button reseeds the loop there, where LaunchServices keeps it registered), and removing it
# destroys no identity because the live bundle is left in place.
#
# Dry-run by default (reports the cure, mutates nothing). Arm with LIMEN_CLAUDE_LSREGISTER_HEAL=1 to
# apply — the launch-agent-liveness.py LIMEN_LAUNCHAGENT_HEAL convention (arm once in ~/.limen.env).
# Idempotent. Exit 0 ⟺ zero unassessable ClaudeCode.app REGISTRATIONS remain (or none were found on a
# dry-run); exit 1 if registrations remain, or a dry-run found some to cure (beat signal).
set -uo pipefail

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }

if [ "$(uname 2>/dev/null)" != "Darwin" ]; then
  log "claude-lsregister-heal: non-darwin — inapplicable"
  exit 0
fi

# LIMEN_CLAUDE_LSREGISTER_BIN exists so scripts/tests/heal-claude-lsregister.test.sh can point the
# whole production code path at a stub that implements -dump and -u. Unset in production. Sibling of
# the LIMEN_TCC_LSREGISTER_DUMP seam in cli/tests/test_tcc_identity_audit.py.
LSREG="${LIMEN_CLAUDE_LSREGISTER_BIN:-/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Support/lsregister}"
CLAUDE_SHARE="${HOME}/.local/share/claude"
VERSIONS_DIR="${CLAUDE_SHARE}/versions"
TRASH="${HOME}/.Trash"
CLI_TARGET="$(readlink -f "${HOME}/.local/bin/claude" 2>/dev/null || true)"

if [ ! -x "$LSREG" ]; then
  log "claude-lsregister-heal: lsregister not found — inapplicable"
  exit 0
fi

ARMED=0
[ "${LIMEN_CLAUDE_LSREGISTER_HEAL:-0}" = 1 ] && ARMED=1
[ "${1:-}" = "--apply" ] && ARMED=1   # the sensor-injected arm (args_when on the dialogs-silenced valve)

# Every ClaudeCode.app path LaunchServices currently has registered.
enumerate() {
  "$LSREG" -dump 2>/dev/null \
    | grep -oE '/[^ ()]*ClaudeCode\.app' \
    | sort -u
}

# True iff $1 is a registration we are allowed to drop: a safe-prefix path (never the CLI or
# versions/) whose bundle FAILS `codesign --verify --strict` for ANY reason.
#
# Widened 2026-08-05. The prior filter matched one exact string ("code has no resources but signature
# indicates they must be present") and therefore MISSED the state macOS actually renders as
# "damaged": mid-write, after the vendor's writeFile(Info.plist) and before its link(), the bundle
# advertises CFBundleExecutable=claude pointing at a file that does not exist yet and codesign
# reports "code object is not signed at all" — no match, left registered. An exact-string filter is a
# fail-closed test used as fail-open safety. Any non-zero verdict is unassessable, and unassessable
# is the whole condition; a bundle that PASSES is still left alone.
condemnable() {
  local p="$1"
  case "$p" in "$CLAUDE_SHARE"/*|"$TRASH"/*) : ;; *) return 1 ;; esac
  [ -n "$CLI_TARGET" ] && [ "$p" = "$CLI_TARGET" ] && return 1
  case "$p" in "$VERSIONS_DIR"/*) return 1 ;; esac
  codesign --verify --strict "$p" >/dev/null 2>&1 && return 1
  return 0
}

found=0
FAST_PATH=""

# 0) FAST PATH — cure the KNOWN path before paying for enumeration. ARMED RUNS ONLY.
#
#    Measured on this host 2026-08-05: `lsregister -dump` costs 2.99s; `codesign --verify --strict`
#    on one known path costs 0.009s. That is 332x, and it sits directly inside the window this
#    class is judged by — the WatchPaths agent's ThrottleInterval (10s) plus however long this
#    script takes to reach the unregistration. Enumerating first spends ~3s of that window
#    rediscovering a path we already know the vendor writes on every start (its own `_jb()` targets
#    exactly $CLAUDE_SHARE/ClaudeCode.app), so time-to-unregister drops from ~13s to ~10s.
#
#    IT IS AN OPTIMIZATION, NEVER A FILTER. The full enumeration still runs and stays
#    authoritative; anything this misses — a ~/.Trash reseed, a second store, a bundle whose `-u`
#    errors for some other reason — is caught there exactly as before. Narrowing the *scan* to the
#    known path would be the same mistake `condemnable()` already made once in this class.
#
#    WHY `-u`'s EXIT CODE IS THE FINDING TEST. `condemnable()` answers "is this bundle
#    unassessable", not "is it registered" — and the steady state is present-and-unassessable-and-
#    unregistered, so acting on `condemnable()` alone would log a cure on every single beat and
#    turn the count into noise. Measured 2026-08-05: `lsregister -u` exits 0 when it actually
#    removed a registration and 1 (`-10814`) when there was none, so the exit code IS the signal.
#    A non-zero exit here means "nothing was registered, or this needs the slow path" — both of
#    which are correctly handled by falling through to the enumeration.
#
#    DRY RUNS SKIP THIS. A dry run's job is an accurate report, and without a dump it cannot know
#    whether the bundle is registered; latency does not matter when nothing is being cured. So the
#    unarmed path stays exactly as it was — the enumeration reports it, once.
KNOWN="$CLAUDE_SHARE/ClaudeCode.app"
if [ "$ARMED" = 1 ] && [ -d "$KNOWN" ] && condemnable "$KNOWN"; then
  if "$LSREG" -u "$KNOWN" 2>/dev/null; then
    FAST_PATH="$KNOWN"
    found=$((found + 1))
    log "claude-lsregister-heal: unregistered (fast path, left in place) $KNOWN"
  fi
fi

# 1) Registered unassessable bundles under the safe prefixes — UNREGISTER ONLY, never remove.
#    The file stays so the vendor's early return holds and the TCC identity survives.
while IFS= read -r p; do
  [ -n "$p" ] || continue
  condemnable "$p" || continue
  # Already handled above. Skipping keeps `found` a count of DISTINCT bundles: in a dry run the
  # enumeration still lists it (nothing was unregistered), and double-counting one bundle as two
  # findings would make the beat's number a lie in the direction that looks worse.
  [ -n "$FAST_PATH" ] && [ "$p" = "$FAST_PATH" ] && continue
  found=$((found + 1))
  if [ "$ARMED" = 1 ]; then
    "$LSREG" -u "$p" 2>/dev/null && log "claude-lsregister-heal: unregistered (left in place) $p"
  else
    log "claude-lsregister-heal: would unregister (leaving in place): $p"
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
      rm -rf "$t" && log "claude-lsregister-heal: swept trashed copy $t"
    else
      log "claude-lsregister-heal: would sweep trashed copy: $t"
    fi
  done <<EOF
$(find "$TRASH" -maxdepth 1 -name '*ClaudeCode*.app' 2>/dev/null)
EOF
fi

# 3) Re-verify: how many unassessable registrations survive?
remaining=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  condemnable "$p" && remaining=$((remaining + 1))
done <<EOF
$(enumerate)
EOF

if [ "$remaining" -eq 0 ] && { [ "$ARMED" = 1 ] || [ "$found" -eq 0 ]; }; then
  log "claude-lsregister-heal: inert (0 unassessable ClaudeCode.app registrations)"
  exit 0
fi
if [ "$ARMED" != 1 ]; then
  log "claude-lsregister-heal: found $found unassessable registration(s) — arm LIMEN_CLAUDE_LSREGISTER_HEAL=1 and re-run to cure"
  exit 1
fi
log "claude-lsregister-heal: $remaining unassessable registration(s) still present after cure"
exit 1
