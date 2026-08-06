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
#
# `-u`'s EXIT CODE IS MODELLED, not assumed. Measured against the real lsregister 2026-08-05:
#   registered path   -> exit 0, and the entry is gone from -dump
#   unregistered path -> exit 1, "failed to scan <path>: -10814 from spotlight"
# The effector's fast path reads that code to tell "I cured something" from "there was nothing to
# cure", so a stub that always exits 0 would make the noise guard untestable — and would have let a
# cure be logged on every beat in the steady state.
make_stub() {
  cat >"$1" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  # REG_DUMP_EMPTY blinds -dump while leaving -u honest. It exists for exactly one contract: prove
  # the fast path cured the bundle on its own, with the enumeration unable to have found it.
  -dump) [ "${REG_DUMP_EMPTY:-0}" = 1 ] || cat "$REG_FILE" 2>/dev/null ;;
  -u)
    if grep -qxF "$2" "$REG_FILE" 2>/dev/null; then
      grep -vxF "$2" "$REG_FILE" >"$REG_FILE.next" 2>/dev/null
      mv "$REG_FILE.next" "$REG_FILE"
      exit 0
    fi
    exit 1
    ;;
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
# The SEMANTIC claim, not one phrasing. The fast path and the enumeration path both cure, and both
# must say "left in place"; neither may ever say "removed". Pinning an exact sentence made this
# assertion fail when the fast path was added, which is a test breaking on wording rather than on
# behaviour — the same brittleness that took `test_pr_debt_trend` red on main (#1860).
case "$out" in *"left in place"*) ok "reports unregistration, not removal" ;; *) bad "reports unregistration, not removal (got: $out)" ;; esac
case "$out" in *removed*) bad "must never claim removal" ;; *) ok "never claims removal" ;; esac

# --- 2. idempotence: a second run finds nothing and stays clean ----------------------------------
out="$(bash "$HEAL" --apply 2>&1)"; rc=$?
check "idempotent: exit 0" "$rc" "0"
if [ -d "$BUNDLE" ]; then ok "idempotent: bundle still present"; else bad "idempotent: bundle vanished"; fi

# --- 2b. THE FAST PATH'S NOISE GUARD -------------------------------------------------------------
# The steady state after a cure is: bundle PRESENT, still unassessable (it always is — that is the
# whole finding), and UNREGISTERED. `condemnable()` is true in that state, because it answers "is
# this assessable", not "is this registered". So a fast path keyed on condemnable() alone would log
# a cure and count a finding on every single beat, forever — turning the one number the beat
# publishes into noise, in the direction that looks like the bug is still happening.
#
# The guard is `lsregister -u`'s exit code (0 = actually removed a registration). This asserts it.
printf '' >"$REG_FILE"                                   # nothing registered
out="$(bash "$HEAL" --apply 2>&1)"; rc=$?
check "steady state: exit 0" "$rc" "0"
case "$out" in *"fast path"*) bad "steady state must not report a fast-path cure (got: $out)" ;; *) ok "steady state: no phantom cure logged" ;; esac
case "$out" in *inert*) ok "steady state: reports inert" ;; *) bad "steady state: should report inert (got: $out)" ;; esac
if [ -d "$BUNDLE" ]; then ok "steady state: bundle still present"; else bad "steady state: bundle vanished"; fi

# --- 2c. the fast path cures WITHOUT the enumeration having to find it ---------------------------
# lsregister -dump costs 2.99s against codesign's 0.009s (measured 2026-08-05), and that sits inside
# the window macOS can raise the dialog in. Proven here by registering the known bundle and giving
# -dump NOTHING: only the fast path can cure it, so a pass means the fast path really ran.
printf '%s\n' "$BUNDLE" >"$REG_FILE"
cp "$HOME/.local/share/claude/versions/9.9.9" "$BUNDLE/Contents/MacOS/claude" 2>/dev/null || true
out="$(REG_DUMP_EMPTY=1 bash "$HEAL" --apply 2>&1)"
case "$out" in *"fast path"*) ok "fast path cures the known bundle" ;; *) bad "fast path did not fire (got: $out)" ;; esac
check "fast path: registration dropped" "$(wc -l <"$REG_FILE" | tr -d ' ')" "0"
if [ -d "$BUNDLE" ]; then ok "fast path: bundle SURVIVES"; else bad "fast path: bundle was deleted"; fi

# --- 2d. a dry run never uses the fast path ------------------------------------------------------
# A dry run's product is an accurate report, and without a dump it cannot know whether the bundle is
# registered; latency buys nothing when nothing is cured. It must report the finding exactly ONCE.
printf '%s\n' "$BUNDLE" >"$REG_FILE"
out="$(bash "$HEAL" 2>&1)"; rc=$?
check "dry-run: exit 1 (still a beat signal)" "$rc" "1"
case "$out" in *"fast path"*) bad "dry run must not take the fast path (got: $out)" ;; *) ok "dry run skips the fast path" ;; esac
check "dry-run: reports the bundle exactly once" "$(printf '%s\n' "$out" | grep -c 'would unregister')" "1"
check "dry-run: registration untouched by the fast path" "$(wc -l <"$REG_FILE" | tr -d ' ')" "1"

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

# --- 11. SENSOR/EFFECTOR FILTER LOCKSTEP ----------------------------------------------------------
# The class-4b block in dialogs-silenced.sh reimplements condemnable()'s decision in a SECOND file.
# Both narrowed to one exact codesign string for six weeks, so the sensor reported green on exactly
# the state the effector could not cure — a duplicated filter with nothing holding the copies
# together. These assert the widened form survives in BOTH, which is the only property that keeps
# "the sensor said inert" worth anything.
#
# Deliberately a text assertion, not a behavioural one: the failure mode is someone re-narrowing the
# filter while editing one file, and the two files cannot be executed against a shared fixture
# without turning a 400-line beat report into a test harness.
SENSOR="$ROOT/scripts/dialogs-silenced.sh"
EFFECTOR="$ROOT/scripts/heal-claude-lsregister.sh"
for f in "$SENSOR" "$EFFECTOR"; do
  n="$(basename "$f")"
  if grep -q 'codesign --verify --strict' "$f"; then
    ok "lockstep: $n judges by codesign --strict"
  else
    bad "lockstep: $n no longer runs codesign --verify --strict"
  fi
done

# --- 12. THE SENSOR'S OWN VERDICT, behaviourally --------------------------------------------------
# A text assertion can only catch re-introducing one known string; it cannot catch a narrowing that
# uses a different one. This drives the real sensor against the stub and reads what it CONCLUDES —
# the only form that would have caught the original defect, where the sensor printed "inert" over a
# registered mid-write bundle. ~6s, the slowest contract here, and worth it: this is the reading the
# beat publishes.
rm -rf "$BUNDLE"
make_bundle "$BUNDLE" "$HOME/.local/share/claude/versions/9.9.9"
rm -f "$BUNDLE/Contents/MacOS/claude"          # the MID-WRITE state: "code object is not signed at all"
printf '%s\n' "$BUNDLE" >"$REG_FILE"
sensor_out="$(bash "$SENSOR" 2>&1 | grep -i 'ClaudeCode.app' || true)"
case "$sensor_out" in
  *"cannot be assessed"*) ok "sensor: reports a registered mid-write bundle as NOT inert" ;;
  *inert*) bad "sensor: reported INERT over a registered unassessable bundle (the six-week defect)" ;;
  *) bad "sensor: no class-4b verdict at all (got: $sensor_out)" ;;
esac

printf '' >"$REG_FILE"                          # nothing registered — the cured steady state
sensor_out="$(bash "$SENSOR" 2>&1 | grep -i 'ClaudeCode.app' || true)"
case "$sensor_out" in
  *inert*) ok "sensor: reports inert once nothing is registered" ;;
  *) bad "sensor: should read inert with an empty registration set (got: $sensor_out)" ;;
esac

echo
echo "heal-claude-lsregister.test: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
exit 0
