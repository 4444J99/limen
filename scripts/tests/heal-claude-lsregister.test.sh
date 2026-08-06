#!/usr/bin/env bash
# Contracts for scripts/heal-claude-lsregister.sh — the Gatekeeper-inertness effector.
#
# This class shipped five cures across six weeks with ZERO test coverage, and the defect that
# survived all five was a decision-function detail (`condemnable()` matching one exact codesign
# string) that no test ever asked about. These are the contracts that would have caught it.
#
# The load-bearing one is `unregisters_but_does_not_remove`: removal is what destroyed the TCC
# identity that sensor 0g8d exists to keep, and what guaranteed the vendor would recreate the bundle
# on the very next start. See IF-GATEKEEPER-INERT.
#
# Darwin-only: the script fails open off-darwin by design, and `codesign` is the real oracle here.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The seam exists so these contracts can be pointed at a PRIOR revision of the effector and shown to
# FAIL there. A contract that passes against the version it was written to reject proves nothing --
# the #1837 lesson, where eight of nine tests asserted against a platform gate and passed vacuously.
HEAL="${LIMEN_HEAL_SCRIPT_UNDER_TEST:-$ROOT/scripts/heal-claude-lsregister.sh}"
pass=0
fail=0

ok()   { pass=$((pass + 1)); printf '  ok   %s\n' "$1"; }
bad()  { fail=$((fail + 1)); printf '  FAIL %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi; }

if [ "$(uname 2>/dev/null)" != "Darwin" ]; then
  echo "heal-claude-lsregister.test: non-darwin — the effector is inapplicable, skipping"
  exit 0
fi

# A stub lsregister: -dump prints whatever REG_FILE holds; -u removes that line (the real one drops
# the registration, not the file — which is exactly the property under test).
make_stub() {
  cat >"$1" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  -dump) cat "$REG_FILE" 2>/dev/null ;;
  -u)    grep -vxF "$2" "$REG_FILE" >"$REG_FILE.next" 2>/dev/null; mv "$REG_FILE.next" "$REG_FILE" ;;
esac
exit 0
STUB
  chmod +x "$1"
}

# An unassessable bundle of exactly the vendor's construction: hand-written Info.plist over a real
# signed Mach-O. codesign --strict rejects it because a bare-Mach-O signature seals no resources.
make_bundle() {
  local bundle="$1" payload="$2"
  mkdir -p "$bundle/Contents/MacOS"
  printf '<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleExecutable</key><string>claude</string><key>CFBundleIdentifier</key><string>com.anthropic.claude-code</string><key>CFBundlePackageType</key><string>APPL</string></dict></plist>\n' >"$bundle/Contents/Info.plist"
  cp "$payload" "$bundle/Contents/MacOS/claude"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP"
mkdir -p "$HOME/.local/share/claude/versions" "$HOME/.Trash" "$HOME/.local/bin"

# A real signed Mach-O to wrap. /bin/echo is Apple-signed, tiny, and always present.
cp /bin/echo "$HOME/.local/share/claude/versions/9.9.9"
chmod +x "$HOME/.local/share/claude/versions/9.9.9"
ln -sfn "$HOME/.local/share/claude/versions/9.9.9" "$HOME/.local/bin/claude"

STUB_BIN="$TMP/lsregister"
make_stub "$STUB_BIN"
export LIMEN_CLAUDE_LSREGISTER_BIN="$STUB_BIN"
export REG_FILE="$TMP/registrations"

BUNDLE="$HOME/.local/share/claude/ClaudeCode.app"

echo "heal-claude-lsregister.test"

# --- 1. the load-bearing contract: unregister, never remove -------------------------------------
make_bundle "$BUNDLE" "$HOME/.local/share/claude/versions/9.9.9"
printf '%s\n' "$BUNDLE" >"$REG_FILE"
out="$(bash "$HEAL" --apply 2>&1)"; rc=$?
check "unregisters_but_does_not_remove: exit 0" "$rc" "0"
if [ -d "$BUNDLE" ]; then ok "unregisters_but_does_not_remove: bundle SURVIVES"; else bad "unregisters_but_does_not_remove: bundle was deleted"; fi
check "unregisters_but_does_not_remove: registration dropped" "$(wc -l <"$REG_FILE" | tr -d ' ')" "0"
case "$out" in *"unregistered (left in place)"*) ok "reports unregistration, not removal" ;; *) bad "reports unregistration, not removal (got: $out)" ;; esac

# --- 2. idempotence: a second run finds nothing and stays clean ----------------------------------
out="$(bash "$HEAL" --apply 2>&1)"; rc=$?
check "idempotent: exit 0" "$rc" "0"
if [ -d "$BUNDLE" ]; then ok "idempotent: bundle still present"; else bad "idempotent: bundle vanished"; fi

# --- 3. the widened filter: a MID-WRITE bundle is condemnable ------------------------------------
# After the vendor's writeFile(Info.plist) and before its link(), codesign says "code object is not
# signed at all" — which the old exact-string filter did not match, leaving it registered. This is
# the state macOS renders as "damaged".
rm -f "$BUNDLE/Contents/MacOS/claude"
printf '%s\n' "$BUNDLE" >"$REG_FILE"
bash "$HEAL" --apply >/dev/null 2>&1
check "mid-write state is condemnable (the old exact-string filter missed it)" "$(wc -l <"$REG_FILE" | tr -d ' ')" "0"
rm -rf "$BUNDLE"

# --- 4. dry-run mutates nothing and signals the beat ---------------------------------------------
make_bundle "$BUNDLE" "$HOME/.local/share/claude/versions/9.9.9"
printf '%s\n' "$BUNDLE" >"$REG_FILE"
out="$(env -u LIMEN_CLAUDE_LSREGISTER_HEAL bash "$HEAL" 2>&1)"; rc=$?
check "dry-run: exit 1 (beat signal)" "$rc" "1"
check "dry-run: registration untouched" "$(wc -l <"$REG_FILE" | tr -d ' ')" "1"
case "$out" in *"would unregister"*) ok "dry-run: reports the cure" ;; *) bad "dry-run: reports the cure (got: $out)" ;; esac

# --- 5. the env valve arms it, same as --apply ---------------------------------------------------
LIMEN_CLAUDE_LSREGISTER_HEAL=1 bash "$HEAL" >/dev/null 2>&1
check "LIMEN_CLAUDE_LSREGISTER_HEAL=1 arms the cure" "$(wc -l <"$REG_FILE" | tr -d ' ')" "0"

# --- 6. exclusions hold: versions/ and the resolved CLI target are never condemned ---------------
printf '%s\n' "$HOME/.local/share/claude/versions/9.9.9" >"$REG_FILE"
bash "$HEAL" --apply >/dev/null 2>&1
check "never condemns a path under versions/" "$(wc -l <"$REG_FILE" | tr -d ' ')" "1"

# --- 7. a bundle OUTSIDE the safe prefixes is left alone (never ~/Applications) -------------------
mkdir -p "$HOME/Applications"
OUTSIDE="$HOME/Applications/ClaudeCode.app"
make_bundle "$OUTSIDE" "$HOME/.local/share/claude/versions/9.9.9"
printf '%s\n' "$OUTSIDE" >"$REG_FILE"
bash "$HEAL" --apply >/dev/null 2>&1
check "never touches ~/Applications" "$(wc -l <"$REG_FILE" | tr -d ' ')" "1"
if [ -d "$OUTSIDE" ]; then ok "never removes from ~/Applications"; else bad "removed a bundle from ~/Applications"; fi

# --- 8. an ASSESSABLE bundle stays registered (a future properly-sealed helper) -------------------
SEALED="$HOME/.local/share/claude/Sealed.app"
mkdir -p "$SEALED"
cp /bin/echo "$SEALED/binary"   # a plain signed Mach-O passes --strict; not a bundle we condemn
printf '%s\n' "$HOME/.local/share/claude/versions/9.9.9" >"$REG_FILE"
bash "$HEAL" --apply >/dev/null 2>&1
check "leaves an assessable path registered" "$(wc -l <"$REG_FILE" | tr -d ' ')" "1"

# --- 9. the ~/.Trash reseed sweep still REMOVES ---------------------------------------------------
TRASHED="$HOME/.Trash/ClaudeCode.app"
make_bundle "$TRASHED" "$HOME/.local/share/claude/versions/9.9.9"
: >"$REG_FILE"
bash "$HEAL" --apply >/dev/null 2>&1
if [ -d "$TRASHED" ]; then bad "trash sweep: reseed survived"; else ok "trash sweep: reseed removed"; fi

# --- 10. every log line carries a UTC timestamp ---------------------------------------------------
out="$(bash "$HEAL" --apply 2>&1 | head -1)"
case "$out" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z\ *) ok "log lines are timestamped" ;;
  *) bad "log lines are timestamped (got: $out)" ;;
esac

echo
echo "heal-claude-lsregister.test: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
exit 0
