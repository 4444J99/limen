#!/usr/bin/env bash
# rollback.sh — exact inverse of migrate.sh. Restores the prior scattered state from the
# deploy.json ledger + *.premigrate backups. Idempotent, safe to run twice, NEVER delete-first.
# The frozen Archive4T/T7Recovery backups are never modified. Run: bash rollback.sh
set -uo pipefail
HOME="${HOME:-/Users/4jp}"
ROOT="$HOME/Workspace/limen"
CONT="$ROOT/container"; BK="$CONT/backup"; STATE="$CONT/state/deploy.json"
PLIST="$HOME/Library/LaunchAgents/com.limen.heartbeat.plist"
LOCKD="$ROOT/logs/.saturate.lock.d"; LABEL="com.limen.heartbeat"; GUI="gui/$(id -u)"
say(){ printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok(){  printf '   \033[32mok\033[0m %s\n' "$*"; }
warn(){ printf '   \033[33m!!\033[0m %s\n' "$*"; }
ran(){ [ -f "$STATE" ] && python3 -c "import json,sys;print('y' if sys.argv[2] in json.load(open(sys.argv[1])).get('completed_steps',[]) else 'n')" "$STATE" "$1" 2>/dev/null | grep -q y; }

say "0  preflight"; [ -f "$STATE" ] || warn "no deploy.json — falling back to *.premigrate detection"
say "1  quiesce (hold lock)"; mkdir "$LOCKD" 2>/dev/null || true; trap 'rmdir "$LOCKD" 2>/dev/null || true' EXIT

say "2  plist"
if ran S8-plist || [ -e "$BK/$LABEL.plist.premigrate" ]; then
  launchctl bootout "$GUI/$LABEL" 2>/dev/null || true
  cp "$BK/$LABEL.plist.premigrate" "$PLIST"; plutil -lint "$PLIST" >/dev/null || warn "plist lint"
  launchctl bootstrap "$GUI" "$PLIST" 2>/dev/null || true
  launchctl print "$GUI/$LABEL" >/dev/null 2>&1 && ok "plist restored + reloaded" || warn "agent not loaded"
else ok "plist untouched"; fi

say "3  ~/.claude/settings.json"
CS="$HOME/.claude/settings.json"
if [ -L "$CS" ]; then rm -f "$CS"; [ -e "$CS.orig" ] && mv "$CS.orig" "$CS"; ok "settings symlink reverted"; else ok "settings untouched"; fi

say "4  ~/.limen.env (secret)"
if [ -L "$HOME/.limen.env" ]; then
  rm -f "$HOME/.limen.env"
  [ -e "$HOME/.limen.env.premigrate" ] && mv "$HOME/.limen.env.premigrate" "$HOME/.limen.env"
  [ "$(grep -c '^GEMINI_API_KEY=' "$HOME/.limen.env" 2>/dev/null || echo 0)" = "1" ] && ok "secret restored (real file)" || warn "secret key count != 1"
else ok "secret untouched"; fi

say "5  shell rc files (OPTIONAL — re-introduces the leak; DEFAULT SKIP)"
printf '   Restore the 4 rc files to their pre-scrub state INCLUDING the GEMINI_API_KEY line? [y/N] '
read -r ans || ans=N
if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
  for b in "$BK"/.*.premigrate "$BK"/*.premigrate; do
    [ -e "$b" ] || continue; case "$b" in *"$LABEL"*) continue;; esac
    bn="$(basename "$b" .premigrate)"; case "$bn" in .zshrc|.zshenv|.zprofile|.bashrc) cp -p "$b" "$HOME/$bn"; ok "restored $bn (leak re-introduced)";; esac
  done
else ok "kept the scrub (rc files stay clean) — recommended"; fi

say "6  repo"
git -C "$ROOT" rev-parse -q --verify refs/tags/container-pre-deploy >/dev/null 2>&1 \
  && { git -C "$ROOT" reset --soft container-pre-deploy 2>/dev/null && ok "repo reset --soft to container-pre-deploy (working tree preserved)"; } \
  || warn "no container-pre-deploy tag — leaving repo as-is (do NOT git checkout -- .)"

say "7  release lock + verify"
rmdir "$LOCKD" 2>/dev/null || true
[ -L "$HOME/.limen.env" ] && warn "~/.limen.env still a symlink" || ok "~/.limen.env real"
[ -L "$HOME/.claude/settings.json" ] && warn "settings still a symlink" || ok "settings real"
launchctl print "$GUI/$LABEL" >/dev/null 2>&1 && ok "agent loaded" || warn "agent not loaded"
printf '\n\033[1mRollback done.\033[0m Frozen backups untouched. container/{env,backup} leftovers kept (harmless; remove manually once healthy).\n'
