#!/usr/bin/env bash
# migrate.sh — fold the scattered conductor into ONE in-place container (~/Workspace/limen).
#
# DECIDED PATH: git-deploy / zero-move (workflow wf_6fd8a8f7-9fb, 5 paths, adversarially judged).
# The repo STAYS in place. OS-pinned slots that are
# symlink-transparent (~/.limen.env, ~/.claude/settings.json) become ABSOLUTE symlinks INTO the
# container. The retired heartbeat LaunchAgent is never recreated. The 4 leaked GEMINI_API_KEY rc lines
# are scrubbed (matched by KEY NAME, never value).
#
# SAFE: copy->verify->rename, NEVER delete-first. Idempotent (re-runnable). A deploy.json ledger is
# written BEFORE the one near-irreversible touch so rollback.sh can fully restore. Backups to
# Archive4T + T7Recovery are mountpoint-GUARDED (an unplugged volume is SKIPPED, never written to
# the internal disk). The secret value is never printed.
#
# Run ONCE:  bash ~/Workspace/limen/container/migrate.sh
# Undo:      bash ~/Workspace/limen/container/rollback.sh
set -uo pipefail

HOME="${HOME:-/Users/4jp}"
ROOT="$HOME/Workspace/limen"
CONT="$ROOT/container"
ENVDIR="$ROOT/env"
BK="$CONT/backup"
STATE="$CONT/state/deploy.json"
LOCKD="$ROOT/logs/.saturate.lock.d"
BRANCH="heal/conductor-restart-2026-06-16"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RC_FILES=("$HOME/.zshrc" "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.bashrc")

say(){ printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok(){  printf '   \033[32mok\033[0m %s\n' "$*"; }
warn(){ printf '   \033[33m!!\033[0m %s\n' "$*"; }
die(){ printf '\n\033[31mABORT:\033[0m %s\n' "$*" >&2; exit 1; }

ledger(){ python3 - "$STATE" "$@" <<'PY'
import json,sys,os
p=sys.argv[1]; op=sys.argv[2]
os.makedirs(os.path.dirname(p),exist_ok=True)
d=json.load(open(p)) if os.path.exists(p) else {"ts":"","completed_steps":[],"slots":{}}
if   op=="step": d["completed_steps"]=sorted(set(d["completed_steps"]+[sys.argv[3]]))
elif op=="slot": d["slots"][sys.argv[3]]=json.loads(sys.argv[4])
elif op=="set":  d[sys.argv[3]]=json.loads(sys.argv[4])
json.dump(d,open(p,"w"),indent=2)
PY
}
has_step(){ [ -f "$STATE" ] && python3 -c "import json,sys;print('y' if sys.argv[2] in json.load(open(sys.argv[1])).get('completed_steps',[]) else 'n')" "$STATE" "$1" 2>/dev/null | grep -q y; }
sha(){ shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'; }

# ---------------------------------------------------------------- Step 0: PREFLIGHT (read-only)
say "0  PREFLIGHT (read-only — aborts on any fail)"
[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ] || die "git toplevel != $ROOT"
[ "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || warn "branch != $BRANCH (continuing)"
free=$(df -g / | awk 'NR==2{print $4}'); [ "${free:-0}" -gt 80 ] || die "internal free ${free}GiB <= 80 (hard rule)"
[ -e "$HOME/.limen.env" ] || die "~/.limen.env missing"
if [ ! -L "$HOME/.limen.env" ]; then
  [ "$(stat -f '%Lp' "$HOME/.limen.env")" = "600" ] || warn "~/.limen.env not 0600"
  [ "$(grep -c '^GEMINI_API_KEY=' "$HOME/.limen.env")" = "1" ] || die "~/.limen.env: expected exactly 1 GEMINI_API_KEY line"
fi
[ -e "$LOCKD" ] && die "stale lock present: $LOCKD (clear it first)"
if has_step COMPLETE; then ok "deploy.json marked COMPLETE — verifying desired state"; fi
ok "preflight passed (free=${free}GiB; heartbeat remains retired)"
ledger set ts "\"$TS\""

# ---------------------------------------------------------------- Step 1: CHECKPOINT untracked brain
say "1  CHECKPOINT untracked entrypoints (explicit pathspec — NOT git add -A)"
mkdir -p "$ROOT/logs"; [ -f "$ROOT/logs/.gitignore" ] || printf '*\n!.gitignore\n' > "$ROOT/logs/.gitignore"
# SECRET-SAFETY: never let the secret or *.premigrate backups enter git (post-leak hardening)
GI="$ROOT/.gitignore"; touch "$GI"
for pat in 'env/' 'container/backup/' 'container/state/' '*.premigrate' '.limen.env'; do
  grep -qxF "$pat" "$GI" 2>/dev/null || echo "$pat" >> "$GI"
done
git -C "$ROOT" add -- .gitignore scripts/heartbeat.sh scripts/saturate.sh scripts/rebalance.py container logs/.gitignore 2>/dev/null || true
if ! git -C "$ROOT" diff --cached --quiet 2>/dev/null; then
  git -C "$ROOT" -c user.name=limen -c user.email=limen@local commit -q -m "container: checkpoint live untracked entrypoints + deploy machinery"
  ok "committed checkpoint"
else ok "nothing to checkpoint (already committed)"; fi
git -C "$ROOT" rev-parse -q --verify refs/tags/container-pre-deploy >/dev/null 2>&1 || git -C "$ROOT" tag container-pre-deploy
ledger step S1

# ---------------------------------------------------------------- Step 2: container machinery (additive)
say "2  CONTAINER machinery (in-repo, no OS slot touched)"
mkdir -p "$CONT"/{launchd,claude,state,backup}; chmod 700 "$BK"
# merged claude settings = user settings + allow-rules rescued (read-only) from the misplaced Archive4T copy
A4T="/Volumes/Archive4T/.claude/settings.json"
python3 - "$HOME/.claude/settings.json" "$A4T" "$CONT/claude/settings.json" <<'PY'
import json,sys,os
base=sys.argv[1]; extra=sys.argv[2]; out=sys.argv[3]
d=json.load(open(base)) if os.path.exists(base) else {}
allow=set((d.get("permissions",{}) or {}).get("allow",[]))
if os.path.exists(extra):
    e=json.load(open(extra)); allow|=set((e.get("permissions",{}) or {}).get("allow",[]))
d.setdefault("permissions",{})["allow"]=sorted(allow)
json.dump(d,open(out,"w"),indent=2)
PY
python3 -m json.tool "$CONT/claude/settings.json" >/dev/null || die "merged settings.json invalid"
ok "machinery written (merged settings; no heartbeat plist)"
ledger step S2

# ---------------------------------------------------------------- Step 3: SECRET into container (copy->verify)
say "3  SECRET copied into container (value never printed)"
mkdir -p "$ENVDIR"
if [ -L "$HOME/.limen.env" ]; then ok "~/.limen.env already a symlink — secret already in container"; else
  cp -p "$HOME/.limen.env" "$ENVDIR/limen.env"; chmod 600 "$ENVDIR/limen.env"
  cmp -s "$HOME/.limen.env" "$ENVDIR/limen.env" || die "secret copy mismatch"
  [ "$(grep -c '^GEMINI_API_KEY=' "$ENVDIR/limen.env")" = "1" ] || die "container secret: key count != 1"
  echo "$(sha "$ENVDIR/limen.env")  env/limen.env" >> "$BK/MANIFEST"
  ok "secret staged in container/env (verified, sha recorded)"
fi
ledger step S3

if [ "${STAGE_ONLY:-0}" = "1" ]; then
  say "STAGED steps 0-3 — no OS slot touched, system still runs on old wiring."
  printf '   Re-run WITHOUT STAGE_ONLY for the gated cutover (steps 4-13).\n'
  exit 0
fi

# ---------------------------------------------------------------- Step 4: SCRUB rc leaks (gating)
say "4  SCRUB leaked GEMINI_API_KEY from shell rc (key-name match, never value)"
for f in "${RC_FILES[@]}"; do
  [ -f "$f" ] || continue
  if [ "$(grep -c 'GEMINI_API_KEY=' "$f" 2>/dev/null || echo 0)" -gt 0 ]; then
    b="$BK/$(basename "$f").premigrate"; [ -e "$b" ] || cp -p "$f" "$b"
    grep -v 'GEMINI_API_KEY=' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    [ "$(grep -c 'GEMINI_API_KEY=' "$f" 2>/dev/null || echo 0)" -eq 0 ] || { cp -p "$b" "$f"; die "scrub failed on $f (restored)"; }
    ok "scrubbed $(basename "$f")"
  fi
done
ledger step S4

# ---------------------------------------------------------------- Step 5: SECRET slot symlink
say "5  ~/.limen.env -> container (absolute symlink; copy->verify->rename, mv -n)"
if [ -L "$HOME/.limen.env" ] && [ "$(readlink "$HOME/.limen.env")" = "$ENVDIR/limen.env" ]; then ok "already linked"; else
  mv -n "$HOME/.limen.env" "$HOME/.limen.env.premigrate" || die "could not preserve ~/.limen.env (premigrate exists?)"
  ledger slot limen_env "{\"pre\":\"real\",\"bak\":\"$HOME/.limen.env.premigrate\",\"bak_sha\":\"$(sha "$HOME/.limen.env.premigrate")\"}"
  ln -s "$ENVDIR/limen.env" "$HOME/.limen.env"
  [ "$(readlink "$HOME/.limen.env")" = "$ENVDIR/limen.env" ] || die "symlink target wrong"
  bash -c 'set -a; . "$HOME/.limen.env"; set +a; [ -n "${GEMINI_API_KEY:-}" ]' || die "secret not readable via symlink"
  ok "~/.limen.env -> $ENVDIR/limen.env (secret resolves)"
fi
ledger step S5

# ---------------------------------------------------------------- Step 6: SETTINGS slot symlink (hygiene)
say "6  ~/.claude/settings.json -> container (absolute symlink)"
CS="$HOME/.claude/settings.json"
if [ -L "$CS" ] && [ "$(readlink "$CS")" = "$CONT/claude/settings.json" ]; then ok "already linked"; else
  [ -e "$CS" ] && { [ -e "$CS.premigrate" ] || cp -p "$CS" "$CS.premigrate"; mv -n "$CS" "$CS.orig"; }
  ledger slot claude_settings "{\"pre\":\"real\",\"bak\":\"$CS.premigrate\"}"
  ln -s "$CONT/claude/settings.json" "$CS"
  ok "~/.claude/settings.json -> container/claude/settings.json"
fi
ledger step S6

# ---------------------------------------------------------------- Step 7: LEDGER before irreversible
say "7  ledger flushed before cutover"
ledger step S7-ledgered

# ---------------------------------------------------------------- Steps 8-11: retired local scheduler boundary
say "8-11  heartbeat scheduler remains retired"
command -v domus-limen-runtime >/dev/null 2>&1 || die "domus-limen-runtime is required"
domus-limen-runtime retire-heartbeat >/dev/null || die "heartbeat retirement verification failed"
ledger step S11-heartbeat-retired
ok "heartbeat label, plist, and descendants absent"

# ---------------------------------------------------------------- Step 12: backups (mountpoint-guarded)
say "12 backups to frozen tiers (mountpoint-GUARDED)"
backed=0
for V in /Volumes/Archive4T /Volumes/T7Recovery; do
  if /sbin/mount | grep -q " on $V "; then
    d="$V/limen-backups/$TS"; mkdir -p "$d"
    git -C "$ROOT" bundle create "$d/limen.bundle" --all >/dev/null 2>&1 && \
    rsync -a --exclude 'logs/.saturate.lock*' --exclude '.git/index.lock' "$ROOT/" "$d/repo/" && \
    { ( cd "$d" && find repo env -type f -print0 2>/dev/null | xargs -0 shasum -a256 > MANIFEST 2>/dev/null ); ok "backup -> $d"; backed=$((backed+1)); } || warn "backup to $V incomplete"
  else warn "$V not mounted — SKIP (not creating it)"; fi
done

# ---------------------------------------------------------------- Step 13: finalize state
say "13 finalize"
if [ "$backed" -ge 1 ]; then ledger step COMPLETE; ok "migration COMPLETE ($backed frozen backup(s))"; else
  ledger set backups "\"PENDING\""; warn "wiring COMPLETE but 0 backups — re-run to retry Step 12 once a volume is mounted"; fi
printf '\n\033[1mLeft in place for safe rollback:\033[0m *.premigrate originals + container/backup/*.\n'
printf 'Finalize (shred premigrate/rc-plaintext) later via container/finalize.sh after N clean heartbeats.\n'
