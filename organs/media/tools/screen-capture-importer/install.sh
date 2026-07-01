#!/usr/bin/env bash
# install.sh — install the screen-capture importer as a per-user LaunchAgent.
#
# Idempotent. Copies the importer to ~/.local/bin, generates the LaunchAgent plist
# for the CURRENT user (no hardcoded /Users/<name>), and (re)loads it. Uninstall
# with `./install.sh --uninstall`.
set -Eeuo pipefail
cd "$(dirname "$0")"

LABEL="com.user.photos-screen-capture-importer"
BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/photos-screen-capture-importer.sh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Application Support/photos-screen-capture-importer"
CAPTURE_DIR="${CAPTURE_DIR:-$HOME/Pictures/Screen Captures}"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "uninstalled $LABEL (left $BIN and state in place)"
  exit 0
fi

mkdir -p "$BIN_DIR" "$LOG_DIR" "$(dirname "$PLIST")" "$CAPTURE_DIR"
install -m 0755 import-screen-captures.sh "$BIN"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$BIN</string></array>
  <key>WatchPaths</key>
  <array><string>$CAPTURE_DIR</string></array>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/out.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/err.log</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed + loaded $LABEL"
echo "watching: $CAPTURE_DIR"
echo "NOTE: grant Automation->Photos permission or imports fail with AppleScript -4960."
