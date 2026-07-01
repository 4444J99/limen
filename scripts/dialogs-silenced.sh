#!/usr/bin/env bash
# dialogs-silenced.sh — the executable predicate for "no more permission/auth/fingerprint dialogs".
#
# Anthony's standing demand: never be asked for a permission, a fingerprint, or an OS dialog
# again — across Claude, the fleet, and the whole machine. The recurring dialogs are not random;
# they come from THREE security boundaries, and (by design) each can only be lowered by a human
# with privilege. A background agent physically cannot turn off the OS firewall, mint a 1Password
# service account, or widen its own permission gate — that impossibility IS the guardrail. So this
# script does the only honest thing: it names each class, reports whether it is silenced, and prints
# the EXACT one-time cure for any that is not. Each cure is one action, then silent forever.
#
# Idempotent, read-only, no sudo. Run anytime:  bash scripts/dialogs-silenced.sh
# Exit 0  ⟺  every recurring dialog class is silenced (the done-predicate).
set -uo pipefail

gaps=0
green(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
red(){   printf '  \033[31m✗\033[0m %s\n' "$1"; gaps=$((gaps+1)); }
cure(){  printf '      ↳ %s\n' "$1"; }
note(){  printf '      · %s\n' "$1"; }

echo "== dialogs-silenced — the three recurring permission classes =="
echo

# ── 1. Claude Code in-app permission prompts — the highest-volume "asking permission". ──
SETTINGS="$HOME/.claude/settings.json"
mode="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
print((d.get("permissions") or {}).get("defaultMode", ""))
PY
)"
if [ "$mode" = "bypassPermissions" ]; then
  green "Claude prompts: permissions.defaultMode = bypassPermissions (no in-app prompts)"
else
  red "Claude prompts: defaultMode is '${mode:-unset}' — Claude still asks for off-allowlist tools"
  cure "Simplest total cure — edit $SETTINGS, inside \"permissions\": { … } add:  \"defaultMode\": \"bypassPermissions\","
  note "An AI cannot set this for you: disabling one's own approval gate is guard-railed by design."
  note "acceptEdits is NOT enough — it still prompts for Bash. bypassPermissions = truly zero prompts."
  note "Surgical alternative, already homed as L-AGENT-BASH-PROMPT (#183): generalize the trust hook instead of full bypass."
fi
echo

# ── 2. 1Password / Touch-ID — the fingerprint dialogs. ──
# SILENCED when NO automated path calls `op` — then a locked vault can never pop Touch-ID unattended.
# creds-hydrate.py is the only `op` caller; it now reads op ONLY with an explicit --op flag (opt-in),
# so a bare TTY (every daemon beat AND every interactive session) no longer triggers it — that TTY
# clause WAS the storm. A service-account token (the only promptless `op`) is the PERMANENT cure: install
# it ONCE at $SA_FILE and every op:// read goes silent forever — the daemon beat, the op:// lanes, and the
# --sweep-all catch-all all hydrate with ZERO Touch-ID. Absent the token, op stays strictly opt-in (--op),
# so nothing pops unattended either way. Install via scripts/op-service-account.sh. [[macos-tcc-gatekeeper-dialogs-solved]]
CREDS="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/scripts/creds-hydrate.py"
SA_FILE="${LIMEN_OP_SA_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
if [ -f "$CREDS" ] && grep -q 'op_ok = op_can_read_silently() or args\.op' "$CREDS" \
   && ! grep -Eq 'op_ok *=.*running_interactively\(\)' "$CREDS"; then
  green "1Password: op:// reads are OPT-IN (--op only) → no daemon beat or session can pop Touch-ID"
  note "SSH agent routing is also opt-in (LIMEN_USE_1PASSWORD_SSH; organvm/domus-genoma#130) — git is HTTPS, so SSH never hits 1Password either."
  if [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] || { [ -f "$SA_FILE" ] && [ -s "$SA_FILE" ]; }; then
    green "service-account token present → op:// lanes AND --sweep-all hydrate unattended, promptless, forever."
  else
    note "op:// lanes hydrate via 'creds-hydrate --apply --op' at a terminal (one deliberate touch), OR — to go"
    note "promptless FOREVER (no touch, ever) — install the service-account token once:  scripts/op-service-account.sh install"
  fi
else
  red "1Password: creds-hydrate still auto-reads 'op' (no opt-in gate) → can pop Touch-ID unattended"
  cure "Make 'op read' opt-in in scripts/creds-hydrate.py:  op_ok = op_can_read_silently() or args.op  (drop the running_interactively() clause; add a --op flag)."
  note "This is a CODE fix an agent CAN land (no human needed). To also make op:// promptless forever, install a service-account token: scripts/op-service-account.sh install."
fi
echo

# ── 3. macOS Application Firewall — 'python/node wants to accept incoming connections'. ──
FW=/usr/libexec/ApplicationFirewall/socketfilterfw
if [ ! -x "$FW" ]; then
  green "Firewall: socketfilterfw not present — nothing to silence"
elif "$FW" --getglobalstate 2>/dev/null | grep -qi 'disabled'; then
  green "Firewall: application firewall is off → no incoming-connection prompts, ever"
else
  cur_node="$(readlink -f "$(command -v node 2>/dev/null)" 2>/dev/null || true)"
  if [ -n "$cur_node" ] && "$FW" --listapps 2>/dev/null | grep -qF "$cur_node"; then
    green "Firewall: on, but the current node ($cur_node) is allow-listed"
    note "A future 'brew upgrade node' rotates the path and re-prompts — turn the firewall off, or 'brew pin node', to make it durable."
  else
    red "Firewall: on, and the current node is not allow-listed → mcphub (binds all interfaces) will re-prompt"
    cure "Zero prompts forever (recommended — single-user box behind NAT, fully reversible):"
    cure "   sudo $FW --setglobalstate off"
    cure "Or keep the firewall on and allow the one offender (re-prompts on each node upgrade unless you also 'brew pin node'):"
    cure "   N=\"\$(readlink -f \$(command -v node))\"; sudo $FW --add \"\$N\" --unblockapp \"\$N\""
    note "Homed as L-FIREWALL-PROMPT."
  fi
fi
echo

if [ "$gaps" -eq 0 ]; then
  echo "ALL CLEAR — no recurring permission dialog remains. (re-run anytime to confirm it stays so)"
  exit 0
fi
printf '%s class(es) still prompt. Each cure above is ONE one-time action, then silent forever.\n' "$gaps"
echo "Do them, then re-run this script — it must print ALL CLEAR."
echo "(Residual one-offs like 'python wants to access Documents' = grant Full Disk Access to your terminal in"
echo " System Settings ▸ Privacy & Security ▸ Full Disk Access — a catch-all for file-access TCC dialogs.)"
exit 1
